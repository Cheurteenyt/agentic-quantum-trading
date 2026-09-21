"""
Intel Signal Aggregator — Rate-limiting & Smart Batching
=========================================================

Problème: Web-agent peut générer des signaux très fréquents (listings, liquidations, etc.)
Solution: Agréger, batch, et limiter le taux d'émission WS

Principe:
- Cooldown de 30s minimum entre signaux identiques
- Batch toutes les 5s → envoie seul le signal le plus important
- Priorité automatique selon: CRITICAL > HIGH > MEDIUM > LOW
- Deduplication intelligente (pas 10 fois "PEPE listing")
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import IntEnum


class Priority(IntEnum):
    """Signal priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(order=True)
class Signal:
    """Un signal intel à diffuser."""
    priority: int
    timestamp: float = field(compare=False)
    signal_type: str = field(compare=False)
    source: str = field(compare=False)
    data: dict = field(compare=False)
    id: str = field(compare=False)

    def is_similar_to(self, other: 'Signal') -> bool:
        """Check if two signals are essentially the same (for dedup)."""
        return (
            self.signal_type == other.signal_type and
            self.source == other.source and
            self._get_signature() == other._get_signature()
        )

    def _get_signature(self) -> str:
        """Generate signature for deduplication."""
        if self.signal_type == "new_listing":
            return f"{self.data.get('symbol', '')}"
        elif self.signal_type == "whale_movement":
            return f"{self.data.get('wallet', '')}:{self.data.get('token', '')}"
        else:
            import json
            return json.dumps(self.data, sort_keys=True)[:200]


class IntelAggregator:
    """
    Aggregateur intelligent de signaux intel.
    """

    def __init__(
        self,
        cooldown_seconds: int = 30,
        batch_interval: int = 5,
        max_signals_per_batch: int = 1,
        signal_ttl_seconds: int = 3600
    ):
        self.cooldown_seconds = cooldown_seconds
        self.batch_interval = batch_interval
        self.max_signals_per_batch = max_signals_per_batch
        self.signal_ttl_seconds = signal_ttl_seconds

        self.pending_signals: List[Signal] = []
        self.last_signal_by_sig: Dict[str, float] = {}
        self.rate_limit_tracker: Dict[tuple, float] = {}

        self._batch_loop_task = None
        self._cleanup_task = None
        self._broadcast_callback = None

    def set_broadcast_callback(self, callback):
        """Setter for async function that broadcasts to WebSocket clients."""
        self._broadcast_callback = callback

    async def start(self):
        """Démarrer les boucles de background."""
        self._batch_loop_task = asyncio.create_task(self._batch_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        print(f"[INTEL-AGG] Started with {self.cooldown_seconds}s cooldown, {self.batch_interval}s batch interval")

    async def stop(self):
        """Arrêter les boucles de background."""
        if self._batch_loop_task:
            self._batch_loop_task.cancel()
            try:
                await self._batch_loop_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        print("[INTEL-AGG] Stopped")

    async def submit_signal(
        self,
        signal_type: str,
        source: str,
        priority: Priority,
        data: dict,
        signal_id: str = None
    ):
        """Soumettre un nouveau signal pour diffusion."""
        now = time.time()

        if signal_id is None:
            import uuid
            signal_id = f"sig_{int(now * 1000)}_{uuid.uuid4().hex[:8]}"

        signal = Signal(
            priority=priority.value,
            timestamp=now,
            signal_type=signal_type,
            source=source,
            data=data,
            id=signal_id
        )

        rate_key = (signal_type, source)
        last_sent = self.rate_limit_tracker.get(rate_key, 0)

        if now - last_sent < self.cooldown_seconds:
            should_upgrade = False
            for i, existing in enumerate(self.pending_signals):
                if existing.is_similar_to(signal):
                    if signal.priority > existing.priority:
                        self.pending_signals[i] = signal
                        print(f"[INTEL-AGG] ↑ Upgraded signal {existing.id}: P{existing.priority} → P{signal.priority}")
                        should_upgrade = True
                    else:
                        print(f"[INTEL-AGG] ↓ Skipped duplicate signal (cooldown)")
                    break

            if not should_upgrade:
                return

        self.pending_signals.append(signal)
        self.last_signal_by_sig[signal._get_signature()] = now
        print(f"[INTEL-AGG] Queue: {len(self.pending_signals)} signals pending")

    async def _batch_loop(self):
        """Boucle principale de batching."""
        while True:
            try:
                await asyncio.sleep(self.batch_interval)

                if not self.pending_signals:
                    continue

                sorted_signals = sorted(
                    self.pending_signals,
                    key=lambda s: (-s.priority, -s.timestamp)
                )

                top_signals = sorted_signals[:self.max_signals_per_batch]

                for signal in top_signals:
                    await self._emit_signal(signal)

                emitted_ids = {s.id for s in top_signals}
                self.pending_signals = [s for s in self.pending_signals if s.id not in emitted_ids]

                for signal in top_signals:
                    rate_key = (signal.signal_type, signal.source)
                    self.rate_limit_tracker[rate_key] = signal.timestamp

                if top_signals:
                    print(f"[INTEL-AGG] Emitted {len(top_signals)} signal(s), {len(self.pending_signals)} remaining")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[INTEL-AGG] Error in batch loop: {e}")

    async def _emit_signal(self, signal: Signal):
        """Émettre un signal via WebSocket."""
        try:
            payload = {
                "type": "intel_signal",
                "payload": {
                    "id": signal.id,
                    "type": signal.signal_type,
                    "source": signal.source,
                    "priority": Priority(signal.priority).name,
                    "data": signal.data,
                    "timestamp": signal.timestamp,
                },
                "ts": time.time(),
            }

            if self._broadcast_callback:
                await self._broadcast_callback(payload)
            else:
                print(f"[INTEL-AGG] Would broadcast but no callback set!")

        except Exception as e:
            print(f"[INTEL-AGG] Failed to emit signal {signal.id}: {e}")

    async def _cleanup_loop(self):
        """Nettoyer les signaux expirés périodiquement."""
        while True:
            try:
                await asyncio.sleep(300)

                now = time.time()
                old_signatures = [
                    sig for sig, ts in self.last_signal_by_sig.items()
                    if now - ts > self.signal_ttl_seconds
                ]

                for sig in old_signatures:
                    del self.last_signal_by_sig[sig]

                if old_signatures:
                    print(f"[INTEL-AGG] Cleaned up {len(old_signatures)} expired signatures")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[INTEL-AGG] Cleanup error: {e}")


# =========================================================
# Instance globale
# =========================================================
aggregator = IntelAggregator(
    cooldown_seconds=30,
    batch_interval=5,
    max_signals_per_batch=1,
    signal_ttl_seconds=3600
)


def get_aggregator() -> IntelAggregator:
    """Get the global aggregator instance."""
    return aggregator


async def start_aggregator():
    """Démarrer l'aggregator avec le bon callback broadcast."""
    from services.websocket_manager import manager as ws_mgr
    aggregator.set_broadcast_callback(ws_mgr.broadcast)
    await aggregator.start()
    print("[INTEL-AGG] Initialized with WebSocket broadcast callback")


def stop_aggregator():
    """Arrêter l'aggregator."""
    if aggregator._batch_loop_task or aggregator._cleanup_task:
        asyncio.create_task(aggregator.stop())
        print("[INTEL-AGG] Stopping...")


# =========================================================
# Auto-scan Loop — Binance Hunter toutes les 30s
# =========================================================

_auto_scan_task = None


async def start_auto_scan():
    """Démarre la boucle automatique de scans."""
    global _auto_scan_task

    async def run_loop():
        from services.web_agent import get_specialized_agents

        interval = 30
        print(f"[INTEL AUTO-SCAN] Starting loop every {interval}s")

        while True:
            try:
                agents = get_specialized_agents()
                hunter = agents["binance_hunter"]

                listings = await hunter.hunt_new_listings()

                if listings:
                    for listing in listings:
                        await aggregator.submit_signal(
                            signal_type="new_listing",
                            source="binance_hunter",
                            priority=Priority.CRITICAL,
                            data=listing,
                            signal_id=f"scan_{int(time.time())}",
                        )

                    print(f"[INTEL AUTO-SCAN] Found {len(listings)} new listing(s)")

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[INTEL AUTO-SCAN] Error: {e}")
                await asyncio.sleep(interval * 2)

    _auto_scan_task = asyncio.create_task(run_loop())
    print("[INTEL AUTO-SCAN] Started (30s interval)")


def stop_auto_scan():
    """Arrête la boucle automatique."""
    global _auto_scan_task
    if _auto_scan_task:
        _auto_scan_task.cancel()
        try:
            asyncio.create_task(_auto_scan_task)
        except:
            pass
        print("[INTEL AUTO-SCAN] Stopped")
