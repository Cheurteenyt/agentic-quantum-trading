"""
Smart Engine — Détection de signaux anormaux en temps réel
==========================================================
Reçoit les trades bruts du Collector et applique des filtres algorithmiques
pour détecter les mouvements de marché significatifs.

Objectif : Transformer le bruit du marché en signaux tradeables.
"""

import time
from collections import deque


class TradeSignal:
    """Représente un signal détecté."""
    def __init__(self, signal_type: str, strength: str, coin: str, message: str, details: dict = None):
        self.type = signal_type
        self.strength = strength  # LOW, MEDIUM, HIGH, CRITICAL
        self.coin = coin
        self.message = message
        self.details = details or {}
        self.timestamp = time.time()

    def to_dict(self):
        return {
            "type": self.type,
            "strength": self.strength,
            "coin": self.coin,
            "message": self.message,
            "timestamp": self.timestamp,
            "details": self.details
        }


class SmartEngine:
    """Cœur de l'analyse algorithmique."""

    def __init__(self):
        self.signals: list[TradeSignal] = []
        self.max_signals = 100
        
        # Buffers pour analyse temporelle
        self.recent_trades = {}  # {coin: deque of trades}
        self.buffer_size = 200   # Analyser les 200 derniers trades
        
        # Cooldown entre détections de cascade (évite le flood)
        self._last_cascade_alert = {}  # {coin: timestamp_last_alert}
        self.cascade_cooldown = 60.0   # 1 cascade max par minute
        
        # Thresholds (configurables)
        self.whale_threshold_usd = 500_000  # Alerte si un trade > 500k$
        self.cascade_threshold_count = 45   # 45 trades consécutifs même sens = cascade (augmenté)
        self.cascade_time_window = 10.0     # ... en moins de 10 secondes (augmenté)

    def on_trade(self, coin: str, price: float, size: float, side: str, ts: float):
        """
        Appelé à CHAQUE trade du WebSocket.
        Analyse la transaction et détecte les anomalies.
        """
        notional = price * size
        
        # Init buffer si besoin
        if coin not in self.recent_trades:
            self.recent_trades[coin] = deque(maxlen=self.buffer_size)
        
        self.recent_trades[coin].append({
            "price": price, "size": size, "side": side, "ts": ts, "notional": notional
        })

        # 1. WHALE DETECTION
        if notional > self.whale_threshold_usd:
            self._add_signal(
                signal_type="WHALE_ENTRY",
                strength="HIGH" if notional > 1_000_000 else "MEDIUM",
                coin=coin,
                message=f"Whale detected: {side} ${notional:,.0f} @ {price}",
                details={"side": side, "size": size, "price": price}
            )

        # 2. LIQUIDATION CASCADE DETECTION
        self._detect_cascade(coin)

    def _detect_cascade(self, coin: str):
        """Détecte une série de trades unidirectionnels (liquidations)."""
        if coin not in self.recent_trades:
            return

        # Cooldown : pas plus d'une alerte par minute
        now = time.time()
        if coin in self._last_cascade_alert and (now - self._last_cascade_alert[coin]) < self.cascade_cooldown:
            return

        trades = list(self.recent_trades[coin])
        if len(trades) < self.cascade_threshold_count:
            return

        # Prendre les N derniers trades
        window = trades[-self.cascade_threshold_count:]
        now_ts = window[-1]["ts"]
        first = window[0]["ts"]
        
        # Vérifier la fenêtre de temps
        time_span = now_ts - first
        if time_span > self.cascade_time_window:
            return

        # Vérifier l'unidirectionnalité avec ratio très élevé (95%+)
        sides = [t["side"] for t in window]
        buy_count = sides.count("B")
        sell_count = sides.count("S")
        
        dominance = max(buy_count, sell_count)
        ratio = dominance / self.cascade_threshold_count
        
        if ratio > 0.92: # 92% des trades sont dans le même sens (plus strict)
            direction = "BUY" if buy_count > sell_count else "SELL"
            self._last_cascade_alert[coin] = now_ts
            self._add_signal(
                signal_type="LIQUIDATION_CASCADE",
                strength="CRITICAL" if ratio > 0.98 else "HIGH",
                coin=coin,
                message=f"Cascade détectée: {dominance}/{self.cascade_threshold_count} trades {direction} en {time_span:.1f}s",
                details={"direction": direction, "intensity": ratio}
            )

    def _add_signal(self, signal_type: str, strength: str, coin: str, message: str, details: dict):
        signal = TradeSignal(signal_type, strength, coin, message, details)
        self.signals.append(signal)
        if len(self.signals) > self.max_signals:
            self.signals.pop(0)
        print(f"[ALERT {strength}] {coin}: {message}")

    def get_signals(self, limit: int = 20, strength: str = None):
        """Retourne les signaux récents filtrés par force."""
        filtered = self.signals
        if strength:
            filtered = [s for s in filtered if s.strength == strength]
        
        return [s.to_dict() for s in filtered[-limit:]]

    def get_stats(self, coin: str):
        """Stats rapides pour un coin."""
        if coin not in self.recent_trades:
            return {"error": "No data"}
        
        trades = list(self.recent_trades[coin])
        if not trades:
            return {}

        buys = sum(1 for t in trades if t["side"] == "B")
        sells = sum(1 for t in trades if t["side"] == "S")
        
        vol_buy = sum(t["notional"] for t in trades if t["side"] == "B")
        vol_sell = sum(t["notional"] for t in trades if t["side"] == "S")

        return {
            "total_trades": len(trades),
            "buy_ratio": round(buys / len(trades), 4),
            "volume_imbalance": round((vol_buy - vol_sell) / (vol_buy + vol_sell + 1), 4),
            "total_volume_usd": round(vol_buy + vol_sell, 2)
        }


# Instance globale
engine = SmartEngine()
