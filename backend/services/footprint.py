"""
Footprint & Heatmap Engine — calcule les métriques order flow
===============================================================
Transforme les données raw du collector (trades, orderbook) en :
  - Footprint bars (volume par price level, delta, POC)
  - Orderbook Heatmap (historique de liquidité price x time)
  - Delta bars (buy vs sell volume par candle)
  - Liquidity Imbalances (ratio bid/ask depth)

Lit les données du state du collector, ne se connecte pas au WS.
"""

import time
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


# =========================================================
# FOOTPRINT BAR
# =========================================================

@dataclass
class PriceLevel:
    price: float
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    trade_count: int = 0

    @property
    def total_volume(self):
        return self.bid_volume + self.ask_volume

    @property
    def delta(self):
        return self.ask_volume - self.bid_volume

    @property
    def imbalance(self):
        total = self.bid_volume + self.ask_volume
        if total == 0:
            return 0.0
        return (self.ask_volume - self.bid_volume) / total


@dataclass
class FootprintBar:
    """Une candle avec footprint détaillé."""
    timestamp: float
    open: float = 0.0
    high: float = 0.0
    low: float = float('inf')
    close: float = 0.0
    total_volume: float = 0.0
    total_delta: float = 0.0
    trade_count: int = 0
    levels: dict = field(default_factory=dict)  # price -> PriceLevel
    poc: float = 0.0  # Point of Control
    poc_bid: float = 0.0
    poc_ask: float = 0.0
    cum_delta: float = 0.0  # CVD cumulative
    stacked_imbalance: list = field(default_factory=list)

    def add_trade(self, price: float, size: float, side: str):
        if price <= 0:
            return

        if self.open == 0:
            self.open = price
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.total_volume += size
        self.trade_count += 1

        key = round(price, 2)
        if key not in self.levels:
            self.levels[key] = PriceLevel(price=key)

        lvl = self.levels[key]
        lvl.trade_count += 1
        if side == "B":
            lvl.bid_volume += size
            self.total_delta -= size  # delta = ask - bid
            self.cum_delta -= size
        else:
            lvl.ask_volume += size
            self.total_delta += size
            self.cum_delta += size

    def finalize(self):
        """Calcule POC et stacked imbalances après que tous les trades sont ajoutés."""
        if self.low == float('inf'):
            self.low = self.open

        # POC
        max_vol = 0
        for price, lvl in self.levels.items():
            if lvl.total_volume > max_vol:
                max_vol = lvl.total_volume
                self.poc = price
                self.poc_bid = lvl.bid_volume
                self.poc_ask = lvl.ask_volume

        # Stacked imbalances (3+ levels consécutifs avec imbalance > 70%)
        sorted_prices = sorted(self.levels.keys())
        streak = []
        for p in sorted_prices:
            lvl = self.levels[p]
            if abs(lvl.imbalance) > 0.7 and lvl.total_volume > 0:
                streak.append(p)
            else:
                if len(streak) >= 3:
                    self.stacked_imbalance.append(streak.copy())
                streak = []
        if len(streak) >= 3:
            self.stacked_imbalance.append(streak)

    def to_dict(self) -> dict:
        levels_dict = {}
        for price, lvl in self.levels.items():
            levels_dict[str(price)] = {
                "bid": round(lvl.bid_volume, 4),
                "ask": round(lvl.ask_volume, 4),
                "total": round(lvl.total_volume, 4),
                "delta": round(lvl.delta, 4),
                "imbalance": round(lvl.imbalance, 4),
                "count": lvl.trade_count,
            }
        return {
            "ts": self.timestamp,
            "open": self.open,
            "high": self.high if self.low != float('inf') else self.open,
            "low": self.low if self.low != float('inf') else self.open,
            "close": self.close,
            "volume": round(self.total_volume, 4),
            "delta": round(self.total_delta, 4),
            "cum_delta": round(self.cum_delta, 4),
            "trades": self.trade_count,
            "poc": self.poc,
            "poc_bid": round(self.poc_bid, 4),
            "poc_ask": round(self.poc_ask, 4),
            "stacked_imbalance": self.stacked_imbalance,
            "levels": levels_dict,
        }


# =========================================================
# FOOTPRINT ENGINE
# =========================================================

class FootprintEngine:
    """Gère les footprint bars pour une coin."""

    def __init__(self, coin: str, interval_sec: float = 60.0):
        self.coin = coin
        self.interval = interval_sec
        self.current_bar: Optional[FootprintBar] = None
        self.bars: list[FootprintBar] = []
        self.max_bars = 200  # Garde les 200 dernières candles

    def add_trade(self, price: float, size: float, side: str, ts: float):
        """Ajoute un trade à la footprint courante."""
        if self.current_bar is None or ts - self.current_bar.timestamp >= self.interval:
            # Finalise l'ancienne bar
            if self.current_bar:
                self.current_bar.finalize()
                self.bars.append(self.current_bar)
                if len(self.bars) > self.max_bars:
                    self.bars = self.bars[-self.max_bars:]
            # Crée une nouvelle bar
            self.current_bar = FootprintBar(timestamp=ts)

        self.current_bar.add_trade(price, size, side)

    def flush(self):
        """Force la finalisation de la bar courante."""
        if self.current_bar:
            self.current_bar.finalize()
            self.bars.append(self.current_bar)
            self.current_bar = None

    def get_bars(self, count: int = 50) -> list[dict]:
        """Retourne les dernières N bars."""
        bars = self.bars[-count:]
        if self.current_bar:
            # Clone pour ne pas muter
            temp = FootprintBar(**{
                k: v for k, v in vars(self.current_bar).items()
                if k != 'levels'
            })
            temp.levels = dict(self.current_bar.levels)
            temp.finalize()
            bars.append(temp)
        return [b.to_dict() for b in bars]

    def get_latest_bar(self) -> Optional[dict]:
        """Retourne la bar courante (même non finalisée)."""
        if self.current_bar:
            temp = FootprintBar(**{
                k: v for k, v in vars(self.current_bar).items()
                if k != 'levels'
            })
            temp.levels = dict(self.current_bar.levels)
            return temp.to_dict()
        if self.bars:
            return self.bars[-1].to_dict()
        return None


# =========================================================
# ORDERBOOK HEATMAP
# =========================================================

class OrderbookHeatmap:
    """Capture l'historique de l'orderbook pour générer une heatmap."""

    def __init__(self, coin: str, max_snapshots: int = 500):
        self.coin = coin
        self.snapshots: list = []  # [(ts, bids_dict, asks_dict)]
        self.max_snapshots = max_snapshots

    def capture(self, bids: list, asks: list, ts: float):
        """Capture un snapshot de l'orderbook."""
        bids_dict = {}
        asks_dict = {}

        # Convertit les levels en {price: size}
        for level in bids[:40]:  # Top 40 levels
            px, sz = _parse_level(level)
            if px > 0:
                bids_dict[round(px, 2)] = sz
        for level in asks[:40]:
            px, sz = _parse_level(level)
            if px > 0:
                asks_dict[round(px, 2)] = sz

        self.snapshots.append((ts, bids_dict, asks_dict))
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots = self.snapshots[-self.max_snapshots:]

    def get_heatmap(self, resolution_sec: float = 5.0, levels: int = 30) -> dict:
        """
        Retourne une heatmap aggregée.
        Retourne une structure : {bids: [...], asks: [...]}
        Chaque entrée : [price_index, time_index, size]
        """
        if not self.snapshots:
            return {"bids": [], "asks": [], "min_size": 0, "max_size": 0}

        # Time buckets
        t0 = self.snapshots[0][0]
        time_buckets = int((self.snapshots[-1][0] - t0) / resolution_sec) + 1
        time_buckets = min(time_buckets, 120)  # Max 120 colonnes temps

        # Price levels à surveiller
        price_set = set()
        for _, b, a in self.snapshots:
            price_set.update(b.keys())
            price_set.update(a.keys())
        sorted_prices = sorted(price_set, reverse=True)[:levels * 2]
        price_idx = {p: i for i, p in enumerate(sorted_prices)}

        # Accumulate
        bid_data = defaultdict(float)
        ask_data = defaultdict(float)

        for snap_ts, b, a in self.snapshots:
            t_idx = min(int((snap_ts - t0) / resolution_sec), time_buckets - 1)
            for px, sz in b.items():
                if px in price_idx:
                    bid_data[(price_idx[px], t_idx)] += sz
            for px, sz in a.items():
                if px in price_idx:
                    ask_data[(price_idx[px], t_idx)] += sz

        all_vals = list(bid_data.values()) + list(ask_data.values())
        min_s = min(all_vals) if all_vals else 0
        max_s = max(all_vals) if all_vals else 1

        # Convertit en arrays serializables
        bid_rows = [[p, t, round(s, 4)] for (p, t), s in bid_data.items()]
        ask_rows = [[p, t, round(s, 4)] for (p, t), s in ask_data.items()]

        return {
            "bids": bid_rows,
            "asks": ask_rows,
            "prices": sorted_prices,
            "min_size": round(min_s, 4),
            "max_size": round(max_s, 4),
            "time_span_sec": round(self.snapshots[-1][0] - t0, 1) if len(self.snapshots) > 1 else 0,
        }


# =========================================================
# IMBALANCE ENGINE
# =========================================================

class ImbalanceEngine:
    """Calcule les imbalances bid/ask en temps réel."""

    def __init__(self, coin: str):
        self.coin = coin
        self.history: list = []  # [(ts, bid_depth, ask_depth, ratio)]
        self.max_history = 200

    def update(self, bids: list, asks: list, ts: float):
        """Calcule l'imbalance à partir de l'orderbook."""
        bid_depth = sum(_parse_level(l)[1] for l in bids[:20])
        ask_depth = sum(_parse_level(l)[1] for l in asks[:20])
        total = bid_depth + ask_depth
        ratio = (bid_depth - ask_depth) / total if total > 0 else 0.0

        self.history.append((ts, round(bid_depth, 4), round(ask_depth, 4), round(ratio, 4)))
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_imbalance(self, window: int = 50) -> dict:
        """Retourne l'état d'imbalance récent."""
        recent = self.history[-window:]
        if not recent:
            return {"current": 0, "avg": 0, "history": []}

        current = recent[-1][3]
        avg = sum(r[3] for r in recent) / len(recent)

        return {
            "current": current,
            "avg_50": round(avg, 4),
            "bid_depth": recent[-1][1],
            "ask_depth": recent[-1][2],
            "history": [{"ts": r[0], "ratio": r[3]} for r in recent],
        }


# =========================================================
# HELPERS
# =========================================================

def _parse_level(level) -> tuple[float, float]:
    """Parse un orderbook level en (price, size)."""
    try:
        if isinstance(level, dict):
            px = level.get("px", level.get("price", 0))
            sz = level.get("sz", level.get("size", 0))
            return float(px), float(sz)
        if isinstance(level, (list, tuple)) and len(level) >= 2:
            return float(level[0]), float(level[1])
    except (TypeError, ValueError):
        pass
    return 0.0, 0.0


# =========================================================
# MANAGER — gère toutes les coins
# =========================================================

class FootprintManager:
    """Singleton qui gère tous les engines par coin."""

    def __init__(self):
        self.footprints: dict[str, FootprintEngine] = {}
        self.heatmaps: dict[str, OrderbookHeatmap] = {}
        self.imbalances: dict[str, ImbalanceEngine] = {}
        self.cvd: dict[str, float] = {}

    def get_or_create(self, coin: str, interval_sec: float = 60.0):
        if coin not in self.footprints:
            self.footprints[coin] = FootprintEngine(coin, interval_sec)
            self.heatmaps[coin] = OrderbookHeatmap(coin)
            self.imbalances[coin] = ImbalanceEngine(coin)
            self.cvd[coin] = 0.0

    def process_trade(self, coin: str, price: float, size: float, side: str, ts: float):
        """Appelé quand un trade arrive du collector."""
        self.get_or_create(coin)
        self.footprints[coin].add_trade(price, size, side, ts)
        self.cvd[coin] += size if side == "B" else -size

    def process_orderbook(self, coin: str, bids: list, asks: list, ts: float):
        """Appelé quand l'orderbook est mis à jour."""
        self.get_or_create(coin)
        self.heatmaps[coin].capture(bids, asks, ts)
        self.imbalances[coin].update(bids, asks, ts)

    def get_footprint(self, coin: str, count: int = 50) -> dict:
        engine = self.footprints.get(coin)
        if not engine:
            return {"error": "No data"}
        return {
            "coin": coin,
            "cvd": round(self.cvd.get(coin, 0), 4),
            "bars": engine.get_bars(count),
        }

    def get_heatmap(self, coin: str, resolution: float = 5.0, levels: int = 30) -> dict:
        hm = self.heatmaps.get(coin)
        if not hm:
            return {"error": "No data"}
        return {"coin": coin, "heatmap": hm.get_heatmap(resolution, levels)}

    def get_imbalance(self, coin: str, window: int = 50) -> dict:
        eng = self.imbalances.get(coin)
        if not eng:
            return {"error": "No data"}
        return {"coin": coin, **eng.get_imbalance(window)}


# Instance globale
manager = FootprintManager()
