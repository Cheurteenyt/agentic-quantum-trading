"""
WebSocket Manager — Gestion centralisée des connexions WS
==========================================================

Utilisé par:
- main.py (market broadcast)
- intel.py (intel signal broadcast)
- agents.py (agent progress updates)

Centralisation pour éviter les circular imports.
"""

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    """Gère toutes les connexions WebSocket actives."""
    
    def __init__(self):
        self.active: list[WebSocket] = []
        
    async def connect(self, ws: WebSocket):
        """Accepte une nouvelle connexion WS."""
        await ws.accept()
        self.active.append(ws)
        print(f"[WS] Client connected. Total: {len(self.active)}")
        
    def disconnect(self, ws: WebSocket):
        """Déconnecte un client WS."""
        if ws in self.active:
            self.active.remove(ws)
            print(f"[WS] Client disconnected. Total: {len(self.active)}")
            
    async def broadcast(self, data: dict):
        """Envoie des données à TOUS les clients connectés."""
        dead = []
        # R9 : itérer la liste vivante avec des await entre chaque envoi —
        # un connect()/disconnect() concurrent (rechargement de page) levait
        # RuntimeError: list changed size during iteration, avalé par
        # l'appelant : les clients restants perdaient le tick sans trace.
        for ws in list(self.active):
            try:
                await ws.send_json(data)
            except Exception as e:
                dead.append(ws)
                
        # Nettoyage des clients morts
        for ws in dead:
            self.disconnect(ws)
            
        if self.active:
            print(f"[WS] Broadcast to {len(self.active)} clients")
            
    async def send_to_client(self, ws: WebSocket, data: dict):
        """Envoie des données à un client spécifique."""
        try:
            await ws.send_json(data)
        except Exception:
            pass
    
    def get_active_count(self) -> int:
        """Retourne le nombre de clients connectés."""
        return len(self.active)
    
    def list_connections(self) -> list[str]:
        """Liste les clients connectés (pour debug)."""
        return [f"ws_{i}" for i in range(len(self.active))]


# Instance globale unique — utilisée par tout le système
manager = ConnectionManager()


# =============================================================================
# Helpers pour différents types de messages
# =============================================================================

def market_update(snapshot_data: dict) -> dict:
    """Format standard pour les updates marché."""
    return {
        "type": "market_update",
        "payload": snapshot_data,
        "ts": None  # Sera set par l'appelant si besoin
    }


def intel_signal(signal_data: dict) -> dict:
    """Format standard pour les signaux intel web-agent."""
    return {
        "type": "intel_signal",
        "payload": signal_data,
        "ts": None
    }


def agent_progress(agent_id: str, message: str, details: dict = None) -> dict:
    """Format standard pour les updates de progression d'agent."""
    return {
        "type": "agent_progress",
        "payload": {
            "agent_id": agent_id,
            "message": message,
            "details": details or {}
        },
        "ts": None
    }


def system_alert(level: str, message: str) -> dict:
    """Alerte système (error, warning, info)."""
    return {
        "type": "system_alert",
        "payload": {
            "level": level,
            "message": message
        },
        "ts": None
    }
