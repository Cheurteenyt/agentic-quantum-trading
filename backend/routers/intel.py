"""
Intel Router — Endpoints pour investigations web-agent
======================================================

Expose:
- Lancer investigations via agents spécialisés
- Visualiser enquêtes en cours
- Historique des findings
- Push WebSocket realtime
"""

import time
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from services.web_agent import (
    get_web_agent,
    get_specialized_agents,
    FirecrawlWebAgent,
)
from services.websocket_manager import manager as ws_manager, intel_signal
from services.intel_aggregator import get_aggregator, Priority


router = APIRouter(tags=["intel"])


# =============================================================================
# Request/Response Models
# =============================================================================

class InvestigationRequest(BaseModel):
    goal: str
    url: Optional[str] = None
    timeout: int = 120

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "goal": "Check if there's a new Binance listing for PEPE in the last 10 minutes",
                    "url": "https://www.binance.com/en/support/announcement/new-cryptocurrency-listing",
                    "timeout": 60
                }
            ]
        }


class InvestigationResponse(BaseModel):
    id: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class IntelSignal(BaseModel):
    type: str
    source: str
    priority: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    data: dict
    investigation_id: str
    timestamp: float


# =============================================================================
# Endpoints principaux
# =============================================================================

@router.post("/investigate")
async def launch_investigation(
    request: InvestigationRequest,
    background_tasks: BackgroundTasks
) -> InvestigationResponse:
    """
    Lance une investigation web autonome.

    Retourne immédiatement l'ID d'enquête, résultat asynchrone.
    Le frontend peut poller /intel/investigation/{id} ou s'abonner au WS.
    """
    agent = get_web_agent()

    # Lance investigation asynchrone
    result = await agent.run(
        goal=request.goal,
        url=request.url,
        timeout=request.timeout
    )

    return InvestigationResponse(**result)


@router.post("/hunt/listings")
async def hunt_binance_listings(background_tasks: BackgroundTasks) -> dict:
    """
    Chasse active aux nouveaux listings Binance.

    Utilise le specialized agent BinanceHunter.
    Signaux envoyés via IntelAggregator (rate-limited + batché).
    """
    agents = get_specialized_agents()
    hunter = agents["binance_hunter"]

    listings = await hunter.hunt_new_listings()

    # Envoyer chaque listing trouvé via l'aggregator
    aggregator = get_aggregator()
    for listing in listings:
        inv_id = f"listing_{int(time.time())}_{len(listings)}"

        # Soumettre à l'aggregator (qui gère rate-limit + batching)
        await aggregator.submit_signal(
            signal_type="new_listing",
            source="binance_hunter",
            priority=Priority.CRITICAL,
            data={
                **listing,
                "investigation_id": inv_id,
            },
            signal_id=inv_id,
        )

    return {
        "listings_found": len(listings),
        "listings": listings,
        "broadcast_via": "intel_aggregator",  # Rate-limited automatically
    }


@router.post("/detective/whale")
async def investigate_whale(
    wallet_address: str,
    amount_usd: float,
    direction: str,
    background_tasks: BackgroundTasks
) -> InvestigationResponse:
    """
    Investigation de mouvement whale suspect.

    Ex: Un whale envoie $50M vers Binance → est-ce un dump imminent?
    """
    agents = get_specialized_agents()
    detective = agents["chain_detective"]

    result = await detective.investigate_whale_movement(
        wallet_address=wallet_address,
        amount_usd=amount_usd,
        direction=direction
    )

    return InvestigationResponse(**result)


@router.post("/sentiment/scan")
async def scan_sentiment(
    symbols: str,  # CSV: "BTC,ETH,SOL"
    background_tasks: BackgroundTasks
) -> dict:
    """
    Scan sentiment global pour plusieurs tokens.
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",")]

    agents = get_specialized_agents()
    scanner = agents["sentiment_scanner"]

    sentiment = await scanner.scan_sentiment(symbol_list)

    return {
        "scanned_symbols": symbol_list,
        "sentiment_scores": sentiment,
    }


@router.post("/sentiment/funding-spike")
async def investigate_funding_spike(
    symbol: str,
    funding_rate: float,
    background_tasks: BackgroundTasks
) -> InvestigationResponse:
    """
    Pourquoi le funding rate a spiqué?
    """
    agents = get_specialized_agents()
    scanner = agents["sentiment_scanner"]

    result = await scanner.investigate_funding_spike(symbol, funding_rate)

    return InvestigationResponse(**result)


# =============================================================================
# Endpoints de statut & historique
# =============================================================================

@router.get("/investigations/active")
async def list_active_investigations() -> list[dict]:
    """Liste toutes les investigations actives/récentes."""
    agent = get_web_agent()
    return agent.list_active_investigations()


@router.get("/investigations/{inv_id}")
async def get_investigation_status(inv_id: str) -> dict | None:
    """Récupère le statut/détails d'une investigation spécifique."""
    agent = get_web_agent()
    return agent.get_investigation_status(inv_id)


@router.get("/signals/recent")
async def get_recent_signals(limit: int = 20) -> list[IntelSignal]:
    """
    Récupère les signaux récents générés par les investigations.
    Stockés dans l'état du web-agent.
    """
    # Les signaux sont broadcast via WS mais aussi persistés ici
    agent = get_web_agent()

    # Récupère investigations et filtre celles avec "signal" flag
    all_invs = agent.list_active_investigations()

    # R9 : clamp — limit=0 => [-0:] renvoyait la LISTE ENTIÈRE, limit négatif
    # inversait le sens du slice (même pattern corrigé ailleurs)
    limit = max(1, min(int(limit), 100))

    signals = []
    for inv in all_invs[-limit:]:
        if inv.get("result", {}).get("triggered_signal"):
            signals.append(IntelSignal(
                type=inv["result"]["triggered_signal"]["type"],
                source=inv["result"]["triggered_signal"]["source"],
                priority=inv["result"]["triggered_signal"]["priority"],
                data=inv["result"]["triggered_signal"]["data"],
                investigation_id=inv.get("id"),
                timestamp=inv.get("completed_at", 0)
            ))

    return signals[:limit]


@router.get("/status", tags=["intel"])
async def get_agents_status() -> dict:
    """Statut général des agents et de l'aggregator."""
    agent = get_web_agent()
    aggregator = get_aggregator()

    return {
        "web_agent_initialized": agent is not None,
        "active_investigations_count": len(agent.active_investigations) if agent else 0,
        "specialized_agents": [
            "binance_hunter",
            "chain_detective",
            "sentiment_scanner"
        ],
        "aggregator_status": {
            "active": aggregator._batch_loop_task is not None,
            "pending_signals": len(aggregator.pending_signals),
            "rate_limit_rules": list(aggregator.rate_limit_tracker.keys()),
            "cooldown_seconds": aggregator.cooldown_seconds,
            "batch_interval": aggregator.batch_interval,
        },
    }


@router.post("/test/signal", tags=["intel"])
async def test_signal_broadcast() -> dict:
    """
    TEST ENDPOINT — Envoyer un signal de test pour vérifier le pipeline.

    Utilise l'aggregator qui appliquera rate-limiting + batching.
    Vérifie que WS broadcast fonctionne.
    """
    from services.intel_aggregator import get_aggregator

    aggregator = get_aggregator()

    # Simuler un signal de test
    await aggregator.submit_signal(
        signal_type="test_signal",
        source="manual_test",
        priority=Priority.MEDIUM,
        data={
            "message": "Signal de test depuis l'API",
            "timestamp": time.time(),
            "test_id": f"test_{int(time.time())}",
        },
    )

    return {
        "success": True,
        "message": "Test signal submitted to aggregator",
        "pending_queue_size": len(aggregator.pending_signals),
        "will_broadcast_in_seconds": aggregator.batch_interval,
    }


# =============================================================================
# WebSocket Broadcast pour Intel Signals
# =============================================================================

async def broadcast_intel_signal(signal: dict):
    """
    Broadcast un signal intel à tous les clients WebSocket connectés.
    Utilise le ws_manager global centralisé.
    """
    # Ajoute type pour routing frontend
    enriched_signal = {
        "type": "intel_signal",
        "payload": signal,
        "ts": time.time()
    }

    # Broadcast via le manager WS centralisé
    await ws_manager.broadcast(enriched_signal)
