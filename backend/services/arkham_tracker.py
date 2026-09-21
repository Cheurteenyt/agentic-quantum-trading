"""
Arkham Tracker — Real-time Smart Money Tracking
=================================================

Ce module est le CŒUR du système de tracking Hermes.
Il utilise la base de données des labels Arkham (scrapés via Firecrawl)
pour identifier en temps réel les mouvements des entités connues.

ARCHITECTURE:
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  Blockchain   │────▶│ ArkhamTracker │────▶│  Hermes      │
│  WebSocket    │     │  (Ce module)  │     │  Frontend    │
│  (Etherscan,  │     │               │     │  Dashboard   │
│   Helius,     │     │  Lookup DB    │     └──────────────┘
│   QuickNode)  │     │  Arkham labels│
└──────────────┘     └───────┬───────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌──────────┐   ┌──────────┐   ┌──────────┐
       │SmartEngine│   │OppEngine │   │IntelAgg  │
       │(anomalie)│   │(flows)   │   │(signaux) │
       └──────────┘   └──────────┘   └──────────┘

FONCTIONNEMENT:
1. Le Collector reçoit les trades Hyperliquid WS
2. Pour chaque trade, le tracker vérifie si l'adresse est dans la DB Arkham
3. Si oui → identifie l'entité (Binance, Jump, etc.) + type (hot/cold/deposit)
4. Génère un signal enrichi avec le contexte de l'entité
5. Envoie le signal au SmartEngine + OpportunityEngine + IntelAggregator

DONNÉES ON-CHAIN SUPPLÉMENTAIRES:
- Etherscan WebSocket pour les transactions Ethereum
- Helius/Solana WebSocket pour les transactions Solana
- Ces flux sont matchés contre la DB Arkham pour identifier les transferts
  entre entités connues (ex: Binance → Jump Trading = signal bearish)

SIGNALS GÉNÉRÉS:
- EXCHANGE_DEPOSIT:    Wallet identifié → Exchange = vente probable
- EXCHANGE_WITHDRAWAL: Exchange → Wallet identifié = accumulation
- WHALE_TRANSFER:      Entité → Entité = mouvement institutionnel
- SMART_MONEY_ACCUM:   Fund connu accumule un token
- SMART_MONEY_DIST:    Fund connu distribue un token
- INSIDER_PATTERN:     Transfert vers exchange avant listing/annonce
"""

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger("arkham_tracker")

from services.arkham_scraper import ArkhamDatabase, get_arkham_db


# =========================================================
# SIGNAL TYPES & PRIORITIES
# =========================================================

class TrackerPriority(IntEnum):
    """Priorité des signaux du tracker."""
    LOW = 1       # Mouvement normal d'exchange
    MEDIUM = 2    # Mouvement whale identifié
    HIGH = 3      # Smart money movement
    CRITICAL = 4  # Insider pattern ou mouvement massif


class TrackerSignalType:
    """Types de signaux générés par le tracker."""
    EXCHANGE_DEPOSIT = "EXCHANGE_DEPOSIT"         # Token va VERS un exchange → sell pressure
    EXCHANGE_WITHDRAWAL = "EXCHANGE_WITHDRAWAL"    # Token sort D'UN exchange → accumulation
    WHALE_TRANSFER = "WHALE_TRANSFER"              # Entité → Entité identifiée
    SMART_MONEY_ACCUM = "SMART_MONEY_ACCUM"        # Fund/VC accumule
    SMART_MONEY_DIST = "SMART_MONEY_DIST"          # Fund/VC distribue
    INSIDER_PATTERN = "INSIDER_PATTERN"             # Pattern suspect pré-listing
    ENTITY_FLOW_ANOMALY = "ENTITY_FLOW_ANOMALY"     # Flow anormal pour une entité
    CROSS_ENTITY_TRANSFER = "CROSS_ENTITY_TRANSFER" # Transfert entre entités connues


# =========================================================
# DATA MODELS
# =========================================================

@dataclass
class TrackedMovement:
    """Un mouvement on-chain identifié par le tracker."""
    tx_hash: str
    from_address: str
    to_address: str
    from_label: Optional[str] = None    # Label Arkham du sender
    to_label: Optional[str] = None      # Label Arkham du receiver
    from_entity: Optional[str] = None   # Entité du sender
    to_entity: Optional[str] = None     # Entité du receiver
    from_type: Optional[str] = None     # hot/cold/deposit/trading
    to_type: Optional[str] = None
    token_symbol: str = ""
    token_address: str = ""
    amount: float = 0.0
    amount_usd: float = 0.0
    chain: str = "ethereum"
    signal_type: str = ""
    priority: int = TrackerPriority.LOW
    reasoning: str = ""
    ts: float = field(default_factory=time.time)

    @property
    def is_exchange_involved(self) -> bool:
        """Un exchange est-il impliqué dans ce mouvement ?"""
        return self.from_type in ("hot", "cold", "deposit", "trading") or \
               self.to_type in ("hot", "cold", "deposit", "trading")

    @property
    def direction(self) -> str:
        """Direction du flow: 'to_exchange' ou 'from_exchange'."""
        if self.to_type in ("hot", "deposit", "trading"):
            return "to_exchange"
        if self.from_type in ("hot", "deposit", "trading"):
            return "from_exchange"
        return "peer_to_peer"

    def to_dict(self) -> dict:
        return {
            "tx_hash": self.tx_hash,
            "from": {
                "address": self.from_address,
                "label": self.from_label,
                "entity": self.from_entity,
                "type": self.from_type,
            },
            "to": {
                "address": self.to_address,
                "label": self.to_label,
                "entity": self.to_entity,
                "type": self.to_type,
            },
            "token": self.token_symbol,
            "amount": self.amount,
            "amount_usd": round(self.amount_usd, 2),
            "chain": self.chain,
            "signal_type": self.signal_type,
            "priority": TrackerPriority(self.priority).name,
            "direction": self.direction,
            "reasoning": self.reasoning,
            "ts": self.ts,
            "ts_human": datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat(),
        }


@dataclass
class EntityFlowTracker:
    """Tracke les flows cumulés d'une entité sur une fenêtre de temps."""
    entity_slug: str
    inflows_usd: deque = field(default_factory=lambda: deque(maxlen=100))
    outflows_usd: deque = field(default_factory=lambda: deque(maxlen=100))
    total_inflow_24h: float = 0.0
    total_outflow_24h: float = 0.0
    last_movements: deque = field(default_factory=lambda: deque(maxlen=50))

    def add_inflow(self, amount_usd: float, movement: TrackedMovement):
        self.inflows_usd.append((time.time(), amount_usd))
        self.total_inflow_24h += amount_usd
        self.last_movements.append(movement)

    def add_outflow(self, amount_usd: float, movement: TrackedMovement):
        self.outflows_usd.append((time.time(), amount_usd))
        self.total_outflow_24h += amount_usd
        self.last_movements.append(movement)

    @property
    def net_flow_24h(self) -> float:
        return self.total_outflow_24h - self.total_inflow_24h

    def get_stats(self) -> dict:
        return {
            "entity": self.entity_slug,
            "inflow_24h_usd": round(self.total_inflow_24h, 2),
            "outflow_24h_usd": round(self.total_outflow_24h, 2),
            "net_flow_24h_usd": round(self.net_flow_24h, 2),
            "recent_movements": len(self.last_movements),
        }


# =========================================================
# ARKHAM TRACKER — Moteur de tracking temps réel
# =========================================================

class ArkhamTracker:
    """
    Tracker temps réel utilisant les labels Arkham.

    Ce module est appelé pour chaque transaction on-chain détectée.
    Il lookup les adresses dans la DB Arkham et génère des signaux
    enrichis si les adresses sont labellisées.

    INTÉGRATION:
    - collector.py → appelle on_hyperliquid_trade() pour chaque trade
    - etherscan_ws → appelle on_eth_transaction() pour chaque tx
    - Le tracker enrichit et forward au SmartEngine + IntelAggregator
    """

    # Seuils de détection
    THRESHOLDS = {
        "whale_movement_usd": 500_000,        # $500K+ = whale
        "mega_whale_usd": 5_000_000,           # $5M+ = méga whale
        "insider_threshold_usd": 100_000,       # $100K+ vers exchange avant listing
        "flow_anomaly_multiplier": 3.0,         # 3x le flow normal = anomalie
        "entity_flow_baseline_usd": 10_000_000, # Baseline pour flow anomalie
    }

    # Entités considérées comme "smart money"
    SMART_MONEY_ENTITIES = {
        "jump-trading", "wintermute", "cumberland", "gsr-markets",
        "flow-traders", "amber-group", "b2c2", "alameda-research",
        "a16z", "paradigm", "jump-crypto",
    }

    # Types de wallets d'exchange (significatifs pour les flows)
    EXCHANGE_WALLET_TYPES = {"hot", "deposit", "trading", "cold", "treasury"}

    def __init__(self):
        self.db: ArkhamDatabase = get_arkham_db()
        self.entity_flows: dict[str, EntityFlowTracker] = {}
        self.recent_signals: deque[TrackedMovement] = deque(maxlen=200)
        self.total_identified = 0
        self.total_unknown = 0

        # Callbacks
        self._intel_callback = None  # Pour IntelAggregator
        self._ws_callback = None     # Pour WebSocket broadcast

    @staticmethod
    def get_all_entities() -> list[dict]:
        """
        Retourne toutes les entités connues du tracker.
        Utilisé par main.py pour le search endpoint.
        """
        try:
            db = get_arkham_db()
            entities = []
            for slug, data in db.entities_by_name.items():
                if isinstance(data, dict):
                    entities.append({
                        "id": slug,
                        "name": data.get("name", slug),
                        "label": data.get("name", slug),
                        "address": data.get("address", ""),
                        "balance": data.get("balance_usd", "—"),
                    })
            return entities
        except Exception:
            return []

    @staticmethod
    def get_entity(entity_id: str) -> Optional[dict]:
        """
        Lookup une entité par ID ou adresse.
        Utilisé par main.py pour le entity detail endpoint.
        """
        try:
            db = get_arkham_db()
            # Try as slug first
            info = db.get_entity_info(entity_id)
            if info:
                return info
            # Try as address
            wallet = db.lookup_wallet(entity_id)
            if wallet:
                return wallet
            return None
        except Exception:
            return None

    async def start_monitoring(self):
        """
        Start the monitoring loop.
        Currently a no-op placeholder — real monitoring requires
        Ethereum WebSocket (see eth_transaction_listener).
        """
        logger.info("[ARKHAM-TRACKER] Monitoring started (polling mode — configure ETH_WS_URL for real-time)")
        # Keep the task alive without doing anything harmful
        while True:
            await asyncio.sleep(60)

    def set_callbacks(self, intel_callback=None, ws_callback=None):
        """Configure les callbacks pour forward les signaux."""
        self._intel_callback = intel_callback
        self._ws_callback = ws_callback

    # =========================================================
    # IDENTIFICATION — Lookup adresses dans la DB Arkham
    # =========================================================

    def identify_address(self, address: str, chain: str = "ethereum") -> Optional[dict]:
        """
        Identifie une adresse on-chain en utilisant la DB Arkham.

        C'est la fonction CLÉ du système. Pour chaque adresse,
        on vérifie si elle correspond à un wallet labellisé.

        Retourne:
        - dict avec label, entity, type si trouvé
        - None si l'adresse est inconnue
        """
        return self.db.lookup_wallet(address, chain)

    def identify_transaction_parties(
        self,
        from_addr: str,
        to_addr: str,
        chain: str = "ethereum"
    ) -> tuple[Optional[dict], Optional[dict]]:
        """
        Identifie les deux parties d'une transaction.

        Retourne (from_info, to_info) où chaque élément est:
        - dict avec label/entity/type si identifié
        - None si inconnu
        """
        from_info = self.identify_address(from_addr, chain)
        to_info = self.identify_address(to_addr, chain)
        return from_info, to_info

    # =========================================================
    # ANALYSE — Générer des signaux à partir des mouvements
    # =========================================================

    def analyze_movement(
        self,
        tx_hash: str,
        from_addr: str,
        to_addr: str,
        token_symbol: str,
        amount: float,
        amount_usd: float,
        chain: str = "ethereum"
    ) -> Optional[TrackedMovement]:
        """
        Analyse un mouvement on-chain et génère un signal si pertinent.

        C'est la fonction principale appelée par le collector et les
        listeners on-chain. Elle:
        1. Identifie les deux parties de la transaction
        2. Détermine le type de signal (deposit, withdrawal, transfer, etc.)
        3. Calcule la priorité
        4. Génère le raisonnement (pourquoi c'est important)
        5. Enrichit le signal avec le contexte Arkham

        Si aucune des deux adresses n'est identifiée, retourne None
        (pas la peine de signaler un mouvement anonyme).
        """
        from_info, to_info = self.identify_transaction_parties(from_addr, to_addr, chain)

        # Si aucune adresse identifiée → pas de signal
        if not from_info and not to_info:
            self.total_unknown += 1
            return None

        self.total_identified += 1

        # Créer le mouvement de base
        movement = TrackedMovement(
            tx_hash=tx_hash,
            from_address=from_addr,
            to_address=to_addr,
            from_label=from_info.get("label") if from_info else None,
            to_label=to_info.get("label") if to_info else None,
            from_entity=from_info.get("entity_slug", from_info.get("entity_name")) if from_info else None,
            to_entity=to_info.get("entity_slug", to_info.get("entity_name")) if to_info else None,
            from_type=from_info.get("wallet_type") if from_info else None,
            to_type=to_info.get("wallet_type") if to_info else None,
            token_symbol=token_symbol,
            amount=amount,
            amount_usd=amount_usd,
            chain=chain,
        )

        # === CLASSIFICATION DU MOUVEMENT ===

        # 1. EXCHANGE DEPOSIT (vers un exchange = sell pressure)
        if to_info and to_info.get("wallet_type") in self.EXCHANGE_WALLET_TYPES:
            entity = to_info.get("entity_slug", to_info.get("entity_name", ""))
            if entity.lower() in ("binance", "coinbase", "okx", "bybit", "kraken",
                                   "kucoin", "bitfinex", "huobi", "gate-io"):
                movement.signal_type = TrackerSignalType.EXCHANGE_DEPOSIT
                movement.reasoning = (
                    f"{from_info.get('label', from_addr[:10])} deposited "
                    f"{amount_usd:,.0f} USD of {token_symbol} to "
                    f"{to_info.get('label', 'Exchange')} — likely sell pressure"
                )

                # Priorité basée sur le montant
                if amount_usd >= self.THRESHOLDS["mega_whale_usd"]:
                    movement.priority = TrackerPriority.CRITICAL
                elif amount_usd >= self.THRESHOLDS["whale_movement_usd"]:
                    movement.priority = TrackerPriority.HIGH
                else:
                    movement.priority = TrackerPriority.MEDIUM

                # Tracker le flow
                self._track_entity_flow(entity.lower(), amount_usd, "inflow", movement)

        # 2. EXCHANGE WITHDRAWAL (sortie d'exchange = accumulation)
        elif from_info and from_info.get("wallet_type") in self.EXCHANGE_WALLET_TYPES:
            entity = from_info.get("entity_slug", from_info.get("entity_name", ""))
            if entity.lower() in ("binance", "coinbase", "okx", "bybit", "kraken",
                                   "kucoin", "bitfinex", "huobi", "gate-io"):
                movement.signal_type = TrackerSignalType.EXCHANGE_WITHDRAWAL
                movement.reasoning = (
                    f"{to_info.get('label', to_addr[:10]) if to_info else to_addr[:10]} "
                    f"withdrew {amount_usd:,.0f} USD of {token_symbol} from "
                    f"{from_info.get('label', 'Exchange')} — accumulation signal"
                )

                if amount_usd >= self.THRESHOLDS["mega_whale_usd"]:
                    movement.priority = TrackerPriority.CRITICAL
                elif amount_usd >= self.THRESHOLDS["whale_movement_usd"]:
                    movement.priority = TrackerPriority.HIGH
                else:
                    movement.priority = TrackerPriority.MEDIUM

                self._track_entity_flow(entity.lower(), amount_usd, "outflow", movement)

        # 3. CROSS-ENTITY TRANSFER (entre deux entités connues — RARE et TRÈS VALORABLE)
        elif from_info and to_info:
            movement.signal_type = TrackerSignalType.CROSS_ENTITY_TRANSFER
            movement.reasoning = (
                f"Entity-to-entity: {from_info.get('entity_name', 'Unknown')} "
                f"→ {to_info.get('entity_name', 'Unknown')} | "
                f"{amount_usd:,.0f} USD {token_symbol} | "
                f"Cross-entity transfers are rare and significant"
            )
            movement.priority = TrackerPriority.HIGH

            # Si smart money impliqué → CRITICAL
            if (from_info.get("entity_slug", "").lower() in self.SMART_MONEY_ENTITIES or
                to_info.get("entity_slug", "").lower() in self.SMART_MONEY_ENTITIES):
                movement.priority = TrackerPriority.CRITICAL

        # 4. SMART MONEY ACCUMULATION / DISTRIBUTION
        elif from_info and from_info.get("entity_slug", "").lower() in self.SMART_MONEY_ENTITIES:
            movement.signal_type = TrackerSignalType.SMART_MONEY_DIST
            movement.reasoning = (
                f"Smart money {from_info.get('label', from_info.get('entity_name'))} "
                f"sending {amount_usd:,.0f} USD of {token_symbol} — possible distribution"
            )
            movement.priority = TrackerPriority.HIGH if amount_usd > 500_000 else TrackerPriority.MEDIUM

        elif to_info and to_info.get("entity_slug", "").lower() in self.SMART_MONEY_ENTITIES:
            movement.signal_type = TrackerSignalType.SMART_MONEY_ACCUM
            movement.reasoning = (
                f"Smart money {to_info.get('label', to_info.get('entity_name'))} "
                f"receiving {amount_usd:,.0f} USD of {token_symbol} — possible accumulation"
            )
            movement.priority = TrackerPriority.HIGH if amount_usd > 500_000 else TrackerPriority.MEDIUM

        # 5. WALLET IDENTIFIÉ mais pas de pattern spécial
        else:
            movement.signal_type = TrackerSignalType.WHALE_TRANSFER
            identified = from_info or to_info
            label = identified.get("label", "Identified wallet")
            movement.reasoning = f"Identified wallet {label} moved {amount_usd:,.0f} USD of {token_symbol}"
            movement.priority = TrackerPriority.LOW

        # Si on a un signal, l'enregistrer et le forward
        if movement.signal_type:
            self.recent_signals.append(movement)
            awaitable = self._forward_signal(movement)
            # Si on est dans un contexte async, await; sinon juste logger
            if asyncio.get_event_loop().is_running():
                asyncio.create_task(awaitable)

        return movement if movement.signal_type else None

    # =========================================================
    # FLOW TRACKING — Cumuler les flows par entité
    # =========================================================

    def _track_entity_flow(
        self,
        entity_slug: str,
        amount_usd: float,
        direction: str,
        movement: TrackedMovement
    ):
        """Tracke les flows cumulés d'une entité."""
        if entity_slug not in self.entity_flows:
            self.entity_flows[entity_slug] = EntityFlowTracker(entity_slug=entity_slug)

        tracker = self.entity_flows[entity_slug]
        if direction == "inflow":
            tracker.add_inflow(amount_usd, movement)
        else:
            tracker.add_outflow(amount_usd, movement)

        # Vérifier les anomalies de flow
        self._check_flow_anomaly(entity_slug, tracker)

    def _check_flow_anomaly(self, entity_slug: str, tracker: EntityFlowTracker):
        """
        Détecte les anomalies de flow pour une entité.

        Anomalie = flow net significativement au-dessus de la baseline.
        Exemple: Binance reçoit $200M de BTC en 1h (baseline ~$50M) = anomalie.
        """
        net_flow = abs(tracker.net_flow_24h)
        baseline = self.THRESHOLDS["entity_flow_baseline_usd"]

        if net_flow > baseline * self.THRESHOLDS["flow_anomaly_multiplier"]:
            # Anomalie détectée!
            direction = "inflow" if tracker.net_flow_24h < 0 else "outflow"
            signal = TrackedMovement(
                tx_hash="flow_anomaly",
                from_address="aggregate",
                to_address="aggregate",
                from_entity=entity_slug if direction == "outflow" else None,
                to_entity=entity_slug if direction == "inflow" else None,
                signal_type=TrackerSignalType.ENTITY_FLOW_ANOMALY,
                priority=TrackerPriority.HIGH,
                reasoning=(
                    f"FLOW ANOMALY: {entity_slug} has "
                    f"{'received' if direction == 'inflow' else 'sent'} "
                    f"${net_flow/1e6:.1f}M net flow in 24h "
                    f"(baseline: ${baseline/1e6:.0f}M, "
                    f"{net_flow/baseline:.1f}x normal)"
                ),
            )
            self.recent_signals.append(signal)

    # =========================================================
    # HYPERLIQUID INTEGRATION — Enrichir les trades du Collector
    # =========================================================

    def on_hyperliquid_trade(
        self,
        coin: str,
        price: float,
        size: float,
        side: str,
        ts: float
    ) -> Optional[TrackedMovement]:
        """
        Appelé par le Collector pour chaque trade Hyperliquid.

        Les trades Hyperliquid ne montrent pas les adresses on-chain,
        mais on peut enrichir avec le contexte des wallets identifiés
        si on a d'autres sources (Etherscan, etc.).

        Pour l'instant, cette méthode vérifie si le volume du trade
        correspond à un pattern connu d'une entité labellisée.
        """
        # Hyperliquid trades n'ont pas d'adresses → on ne peut pas
        # directement identifier. Mais on peut corréler avec les flows
        # on-chain détectés séparément.
        return None  # Sera enrichi quand on aura les adresses

    # =========================================================
    # ETHEREUM TRANSACTION LISTENER
    # =========================================================

    async def on_eth_transaction(self, tx: dict):
        """
        Traite une transaction Ethereum détectée par le listener.

        Format attendu du tx:
        {
            "hash": "0x...",
            "from": "0x...",
            "to": "0x...",
            "value": "1000000000000000000",  # wei
            "tokenSymbol": "ETH",  # si ERC20 transfer
            "tokenAddress": "0x...",
            "amount": 1.0,
            "amountUsd": 3500.0,
        }
        """
        tx_hash = tx.get("hash", "")
        from_addr = tx.get("from", "")
        to_addr = tx.get("to", "")
        token_symbol = tx.get("tokenSymbol", "ETH")
        amount = tx.get("amount", 0)
        amount_usd = tx.get("amountUsd", 0)

        # Ne signaler que les mouvements > $10K
        if amount_usd < 10_000:
            return None

        movement = self.analyze_movement(
            tx_hash=tx_hash,
            from_addr=from_addr,
            to_addr=to_addr,
            token_symbol=token_symbol,
            amount=amount,
            amount_usd=amount_usd,
            chain="ethereum"
        )

        return movement

    # =========================================================
    # SIGNAL FORWARDING
    # =========================================================

    async def _forward_signal(self, movement: TrackedMovement):
        """
        Forward le signal vers:
        1. IntelAggregator (pour WS broadcast au frontend)
        2. SmartEngine (pour détection d'anomalies)
        3. OpportunityEngine (pour détection d'opportunités)
        4. WebSocket broadcast (pour le dashboard temps réel)
        """
        payload = {
            "type": "arkham_signal",
            "payload": movement.to_dict(),
            "ts": time.time(),
        }

        # 1. IntelAggregator
        if self._intel_callback:
            try:
                from services.intel_aggregator import Priority, aggregator
                priority_map = {
                    TrackerPriority.LOW: Priority.LOW,
                    TrackerPriority.MEDIUM: Priority.MEDIUM,
                    TrackerPriority.HIGH: Priority.HIGH,
                    TrackerPriority.CRITICAL: Priority.CRITICAL,
                }
                await aggregator.submit_signal(
                    signal_type=movement.signal_type,
                    source="arkham_tracker",
                    priority=priority_map.get(movement.priority, Priority.MEDIUM),
                    data=movement.to_dict(),
                )
            except Exception as e:
                logger.warning(f"[ARKHAM-TRACKER] Intel forward error: {e}")

        # 2. WebSocket broadcast
        if self._ws_callback:
            try:
                await self._ws_callback(payload)
            except Exception as e:
                logger.warning(f"[ARKHAM-TRACKER] WS broadcast error: {e}")

    # =========================================================
    # API — Endpoints pour le frontend
    # =========================================================

    def get_recent_signals(self, limit: int = 50) -> list[dict]:
        """Retourne les signaux récents."""
        signals = list(self.recent_signals)[-limit:]
        return [s.to_dict() for s in reversed(signals)]

    def get_entity_flow_summary(self) -> dict:
        """Retourne un résumé des flows par entité."""
        return {
            slug: tracker.get_stats()
            for slug, tracker in self.entity_flows.items()
        }

    def get_exchange_flow_signals(self, exchange: str = None) -> list[dict]:
        """Retourne les signaux de flow pour un exchange spécifique."""
        signals = list(self.recent_signals)
        if exchange:
            signals = [
                s for s in signals
                if exchange.lower() in (s.from_entity or "").lower() or
                   exchange.lower() in (s.to_entity or "").lower()
            ]
        return [s.to_dict() for s in reversed(signals)]

    def get_smart_money_activity(self) -> list[dict]:
        """Retourne l'activité récente du smart money."""
        signals = [
            s for s in self.recent_signals
            if s.signal_type in (
                TrackerSignalType.SMART_MONEY_ACCUM,
                TrackerSignalType.SMART_MONEY_DIST,
                TrackerSignalType.CROSS_ENTITY_TRANSFER,
            )
        ]
        return [s.to_dict() for s in reversed(signals)]

    def get_stats(self) -> dict:
        """Stats du tracker."""
        identified_pct = 0
        total = self.total_identified + self.total_unknown
        if total > 0:
            identified_pct = round(self.total_identified / total * 100, 1)

        return {
            "total_identified_movements": self.total_identified,
            "total_unknown_movements": self.total_unknown,
            "identification_rate_pct": identified_pct,
            "recent_signals_count": len(self.recent_signals),
            "tracked_entities": len(self.entity_flows),
            "db_stats": self.db.get_stats(),
        }


# =========================================================
# INSTANCE GLOBALE
# =========================================================

_tracker_instance: Optional[ArkhamTracker] = None


def get_arkham_tracker() -> ArkhamTracker:
    """Récupère ou crée l'instance du tracker."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = ArkhamTracker()
    return _tracker_instance


# =========================================================
# ETHEREUM TRANSACTION LISTENER (Etherscan WS / Helius)
# =========================================================

async def eth_transaction_listener(
    tracker: ArkhamTracker = None,
    ws_url: str = None,
    monitored_addresses: set = None
):
    """
    Écoute les transactions Ethereum en temps réel via Etherscan WebSocket.

    Pour chaque transaction, vérifie si les adresses sont dans la DB Arkham.
    Si oui, génère un signal enrichi.

    NOTE: Ce listener nécessite un endpoint WebSocket Ethereum.
    Options:
    - Etherscan WebSocket (payant mais fiable)
    - Helius (Solana + Ethereum)
    - QuickNode WebSocket
    - Infura WebSocket

    Pour l'instant, on utilise une approche polling si pas de WS disponible.
    """
    if tracker is None:
        tracker = get_arkham_tracker()

    # Si on a un WS URL, se connecter
    if ws_url:
        import websockets
        logger.info(f"[ETH-LISTENER] Connecting to {ws_url}...")

        while True:
            try:
                async with websockets.connect(ws_url) as ws:
                    # S'abonner aux nouvelles transactions
                    await ws.send(json.dumps({
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newPendingTransactions"]
                    }))

                    async for raw in ws:
                        try:
                            tx_data = json.loads(raw)
                            # Parser et identifier
                            await tracker.on_eth_transaction(tx_data)
                        except json.JSONDecodeError:
                            pass
                        except Exception as e:
                            logger.error(f"[ETH-LISTENER] TX processing error: {e}")

            except Exception as e:
                logger.error(f"[ETH-LISTENER] Connection error: {e}")
                await asyncio.sleep(10)  # Retry après 10s

    else:
        logger.info("[ETH-LISTENER] No WebSocket URL configured — polling mode")
        # Mode polling: vérifier les derniers blocs périodiquement
        # (nécessite Etherscan API key ou autre provider)
        logger.warning("[ETH-LISTENER] Polling mode not implemented yet — configure a WS URL")


# =========================================================
# QUICK BACKTEST — Tester le tracker avec des données historiques
# =========================================================

def backtest_tracker(transactions: list[dict]) -> list[dict]:
    """
    Teste le tracker avec une liste de transactions historiques.

    Permet de valider que les identifications Arkham fonctionnent
    correctement avant de brancher le listener en production.

    Usage:
        transactions = [
            {"hash": "0x...", "from": "0x28c6...", "to": "0x9696...",
             "tokenSymbol": "ETH", "amount": 1000, "amountUsd": 3500000},
            ...
        ]
        results = backtest_tracker(transactions)
    """
    tracker = get_arkham_tracker()
    results = []

    for tx in transactions:
        movement = tracker.analyze_movement(
            tx_hash=tx.get("hash", ""),
            from_addr=tx.get("from", ""),
            to_addr=tx.get("to", ""),
            token_symbol=tx.get("tokenSymbol", "ETH"),
            amount=tx.get("amount", 0),
            amount_usd=tx.get("amountUsd", 0),
            chain=tx.get("chain", "ethereum"),
        )
        if movement:
            results.append(movement.to_dict())

    logger.info(f"[BACKTEST] {len(results)}/{len(transactions)} transactions identified")
    return results
