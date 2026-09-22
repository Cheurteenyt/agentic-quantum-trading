#!/usr/bin/env python
"""Terminal LIVE Aster — le mouvement du lieu d'exécution, en direct.

Réponse à l'objection « on ne voit pas les mouvements sur Aster » : MMT donne
le live sur Binance, PERSONNE ne le donne sur Aster. Ce script ouvre les
streams WebSocket d'Aster (carnet 100 ms + trades + liquidations) et affiche
dans le terminal :

  - le carnet en mouvement (échelle, murs surlignés)
  - la tape des trades (gros trades surlignés, seuil adaptatif)
  - le delta taker cumulé + vitesse 60 s
  - les liquidations en direct
  - le basis Aster vs Binance (rappel : les prix ne sont PAS les mêmes)
  - nos signaux Absorption & Sweep recalculés à chaque bougie 30m fermée

Usage :
  .venv/bin/python scripts/aster_live.py                     # BTCUSDT, infini
  .venv/bin/python scripts/aster_live.py --symbol ETHUSDT --duration 20
  .venv/bin/python scripts/aster_live.py --big-multiple 15   # gros trades + sensibles

Ctrl+C pour arrêter. Stdlib + websockets + rich (déjà dans requirements).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aster_absorption import bars_from_klines, detect, fetch_klines  # noqa: E402
from scripts.basis_guard import last_price, ASTER_TICKER, BINANCE_TICKER  # noqa: E402

WS_BASE = "wss://fstream.asterdex.com/stream?streams="
UP_COLOR = "#1a9850"
DOWN_COLOR = "#d73027"


def stream_url(symbol: str) -> str:
    s = symbol.lower()
    return f"{WS_BASE}{s}@aggTrade/{s}@depth20@100ms/{s}@forceOrder"


def classify(trade_qty: float, median_qty: float, big_multiple: float) -> str:
    """'big' si le trade dépasse N× la médiane des 200 derniers."""
    if median_qty > 0 and trade_qty >= big_multiple * median_qty:
        return "big"
    return "normal"


def fmt_qty(q: float) -> str:
    if q >= 1000:
        return f"{q/1000:,.1f}k"
    if q >= 10:
        return f"{q:.1f}"
    return f"{q:.3f}"


def bar(qty: float, qty_max: float, width: int = 10) -> str:
    if qty_max <= 0:
        return ""
    return "█" * max(1, round(qty / qty_max * width))


class LiveState:
    def __init__(self, symbol: str, big_multiple: float):
        self.symbol = symbol
        self.big_multiple = big_multiple
        self.bids: list[tuple[float, float]] = []
        self.asks: list[tuple[float, float]] = []
        self.trades: deque = deque(maxlen=18)
        self.trade_sizes: deque = deque(maxlen=200)
        self.delta_cum: float = 0.0
        self.delta_window: deque = deque(maxlen=600)  # (ts, delta signé) ~ 100ms*600 = 60s
        self.big_count: int = 0
        self.liqs: deque = deque(maxlen=8)
        self.signals: deque = deque(maxlen=6)
        self.last_signals_poll: float = 0.0
        self.mid: float = 0.0
        self.basis_pct: float | None = None
        self.oi: float | None = None
        self.last_oi_poll: float = 0.0
        self.updated: float = 0.0

    def on_depth(self, bids, asks):
        self.bids = [(float(p), float(q)) for p, q in bids if float(q) > 0]
        self.asks = [(float(p), float(q)) for p, q in asks if float(q) > 0]
        if self.bids and self.asks:
            self.mid = (self.bids[0][0] + self.asks[0][0]) / 2.0
        self.updated = time.time()

    def on_trade(self, price: float, qty: float, is_buyer_maker: bool):
        # is_buyer_maker=True => le taker VEND (agression vendeuse)
        side = -1 if is_buyer_maker else 1
        self.delta_cum += side * qty
        self.delta_window.append((time.time(), side * qty))
        self.trade_sizes.append(qty)
        kind = classify(qty, statistics.median(self.trade_sizes) if len(self.trade_sizes) >= 20 else 0.0,
                        self.big_multiple)
        if kind == "big":
            self.big_count += 1
        self.trades.appendleft((time.time(), price, qty, side, kind))

    def on_liq(self, side: str, qty: float, price: float):
        self.liqs.appendleft((time.time(), side, qty, price))

    def delta_speed_60s(self) -> float:
        cutoff = time.time() - 60
        return sum(d for ts, d in self.delta_window if ts >= cutoff)

    def poll_slow(self):
        """Basis + OI + signaux : REST lent, non bloquant pour les streams."""
        now = time.time()
        if now - self.last_signals_poll > 30:
            self.last_signals_poll = now
            try:
                bars = bars_from_klines(fetch_klines(self.symbol, "30m", limit=400))
                evs = detect(bars)
                for ev in evs[-3:]:
                    b = bars[ev["i"]]
                    self.signals.appendleft((b["t"], ev["kind"], b["c"]))
            except Exception:  # noqa: BLE001 — le live ne doit pas mourir sur le REST
                pass
        if now - self.last_oi_poll > 60:
            self.last_oi_poll = now
            try:
                req = urllib.request.Request(
                    f"https://fapi.asterdex.com/fapi/v1/openInterest?symbol={self.symbol}",
                    headers={"User-Agent": "trading-agent/1.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    self.oi = float(json.load(resp)["openInterest"])
            except Exception:  # noqa: BLE001
                pass
            try:
                aster = last_price(ASTER_TICKER, self.symbol)
                binance = last_price(BINANCE_TICKER, self.symbol)
                self.basis_pct = (aster - binance) / binance * 100.0
            except Exception:  # noqa: BLE001
                self.basis_pct = None


def header_panel(st: LiveState) -> Panel:
    t = Table.grid(padding=(0, 2))
    t.add_column(justify="left"); t.add_column(justify="right")
    t.add_column(justify="left"); t.add_column(justify="right")
    spread = (st.asks[0][0] - st.bids[0][0]) if st.bids and st.asks else 0.0
    basis = f"{st.basis_pct:+.3f} %" if st.basis_pct is not None else "—"
    basis_color = "red" if st.basis_pct is not None and abs(st.basis_pct) >= 0.5 else "dim"
    t.add_row("mid", f"{st.mid:,.2f}", "spread", f"{spread:.2f}")
    t.add_row("Δ cumulé", f"{st.delta_cum:+,.2f}", "Δ 60s", f"{st.delta_speed_60s():+,.2f}")
    t.add_row("gros trades", str(st.big_count), "basis vs Binance", Text(basis, style=basis_color))
    t.add_row("OI", f"{st.oi:,.0f}" if st.oi else "—", "maj",
              datetime.now(tz=timezone.utc).strftime("%H:%M:%S"))
    return Panel(t, title=f"[bold]{st.symbol} — Aster LIVE[/bold]", border_style=ACCENT_BORDER(st))


def ACCENT_BORDER(st: LiveState) -> str:
    return "cyan" if time.time() - st.updated < 2 else "dim"


def ladder_panel(st: LiveState) -> Panel:
    n = 10
    bids = st.bids[:n]
    asks = st.asks[:n]
    qmax = max([q for _, q in bids + asks] or [1.0])
    med = statistics.median([q for _, q in bids + asks]) if (bids or asks) else 0.0
    t = Table.grid(padding=(0, 1))
    t.add_column(justify="right"); t.add_column(justify="left")
    t.add_column(justify="left"); t.add_column(justify="right")
    for i in range(n):
        bp, bq = bids[i] if i < len(bids) else (None, 0)
        ap, aq = asks[i] if i < len(asks) else (None, 0)
        bbar = Text(bar(bq, qmax), style="bold green" if (med and bq >= 5 * med) else "green")
        abar = Text(bar(aq, qmax), style="bold red" if (med and aq >= 5 * med) else "red")
        t.add_row(
            Text(f"{bp:,.1f}" if bp else "—", style="green"),
            bbar,
            abar,
            Text(f"{ap:,.1f}" if ap else "—", style="red"),
        )
    return Panel(t, title="Carnet (murs en gras)", border_style="dim")


def tape_panel(st: LiveState) -> Panel:
    t = Table.grid(padding=(0, 2))
    t.add_column(justify="left"); t.add_column(justify="right")
    t.add_column(justify="right"); t.add_column(justify="left")
    for ts, price, qty, side, kind in list(st.trades)[:14]:
        hh = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")
        style = "bold " + ("green" if side > 0 else "red") if kind == "big" else ("green" if side > 0 else "red")
        mark = " <<" if kind == "big" else ""
        t.add_row(hh, Text(f"{price:,.1f}", style=style),
                  Text(fmt_qty(qty), style=style), Text("ACHAT" if side > 0 else "VENTE", style=style) )
    return Panel(t, title=f"Tape (gros trades surlignés, seuil = {st.big_multiple:g}× médiane)", border_style="dim")


def events_panel(st: LiveState) -> Panel:
    lines = Text()
    if st.liqs:
        for ts, side, qty, price in list(st.liqs)[:4]:
            hh = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M:%S")
            lines.append(f"LIQ  {hh}  {side.upper():<4} {fmt_qty(qty)} @ {price:,.1f}\n",
                         style="bold yellow")
    for ts, kind, close in list(st.signals)[:3]:
        hh = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m %H:%M")
        lines.append(f"SIGNAL  {hh}  {kind}  close={close:,.2f}\n", style="bold magenta")
    if not lines.plain:
        lines.append("… liquidations et signaux apparaîtront ici", style="dim")
    return Panel(lines, title="Liquidations & signaux Aster", border_style="dim")


def render_all(st: LiveState):
    return Group(header_panel(st), ladder_panel(st), tape_panel(st), events_panel(st))


async def rest_loop(st: LiveState):
    while True:
        await asyncio.to_thread(st.poll_slow)
        await asyncio.sleep(5)


async def ws_loop(st: LiveState, duration: float | None):
    delay = 1.0
    start = time.time()
    while duration is None or time.time() - start < duration:
        try:
            async with connect(stream_url(st.symbol), ping_interval=20) as ws:
                delay = 1.0
                async for raw in ws:
                    msg = json.loads(raw)
                    d = msg.get("data", msg)
                    ev = d.get("e")
                    if ev == "aggTrade":
                        st.on_trade(float(d["p"]), float(d["q"]), bool(d["m"]))
                    elif ev == "depthUpdate":
                        st.on_depth(d["b"], d["a"])
                    elif ev == "forceOrder":
                        o = d.get("o", {})
                        st.on_liq(o.get("S", "?"), float(o.get("q", 0)), float(o.get("p", 0)))
                    if duration is not None and time.time() - start >= duration:
                        return
        except Exception as exc:  # noqa: BLE001 — reconnect expo, comme liq_collector
            print(f"[reconnect] {exc} — nouvelle tentative dans {delay:.0f}s", file=sys.stderr)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


def main() -> int:
    p = argparse.ArgumentParser(description="Terminal live Aster (carnet + tape + delta + liqs + signaux)")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--duration", type=float, default=None, help="secondes (test) ; défaut : infini")
    p.add_argument("--big-multiple", type=float, default=25.0)
    args = p.parse_args()

    st = LiveState(args.symbol.upper(), args.big_multiple)
    st.poll_slow()
    refresh = 0.2 if (sys.stdout.isatty()) else 1.0

    async def run():
        with Live(render_all(st), refresh_per_second=int(1 / refresh)) as live:
            ws_task = asyncio.create_task(ws_loop(st, args.duration))
            rest_task = asyncio.create_task(rest_loop(st))
            done_test = args.duration is not None
            while not ws_task.done():
                live.update(render_all(st))
                await asyncio.sleep(refresh)
                if done_test and time.time() - start_t >= args.duration:
                    break
            rest_task.cancel()
            ws_task.cancel()
    start_t = time.time()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
    print(f"\n[fin] Δ cumulé session : {st.delta_cum:+,.2f} · gros trades : {st.big_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
