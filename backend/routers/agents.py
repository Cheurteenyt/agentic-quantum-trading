"""
Router Agents — Declenchement des cycles d'analyse + monitoring
================================================================
Utilise le module agent/ (GLMClient + RiskGuard + StateManager)
au lieu d'un subprocess vers un script inexistant.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router      = APIRouter()
SIGNALS_DIR = Path("data/signals")

# Ajoute la racine du projet pour importer le module agent/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# =========================================================
# MODELS
# =========================================================

class AgentRunRequest(BaseModel):
    crypto:   str  = "BTC"
    symbol:   str  = "XAUUSD"
    live:     bool = False
    interval: int  = 0

# =========================================================
# AGENT STATE
# =========================================================

_agent_task: asyncio.Task | None = None
_agent_status: dict = {"running": False, "last_result": None, "error": None}


async def _run_agent_cycle(crypto: str, symbol: str, live: bool):
    """
    Exécute un cycle d'analyse via GLMClient + RiskGuard.
    Remplace l'ancien subprocess vers agents.py (inexistant).
    """
    global _agent_status
    _agent_status = {"running": True, "last_result": None, "error": None}

    try:
        from agent.client import GLMClient
        from agent.risk_guard import RiskGuard

        client = GLMClient()
        guard  = RiskGuard()

        # Vérifie si le trading est autorisé
        risk_check = guard.can_trade()
        if not risk_check["allowed"]:
            _agent_status = {
                "running": False,
                "last_result": None,
                "error": f"Risk guard: {risk_check['reason']}",
            }
            return

        # Construction du prompt d'analyse
        market_context = f"Analyse {crypto}"
        if live:
            market_context += " en mode live"

        messages = [
            {"role": "system", "content": "Tu es un analyste trading crypto. Réponds en JSON avec les champs: action (BUY/SELL/HOLD), confidence (low/medium/high), reason."},
            {"role": "user", "content": market_context},
        ]

        # Appel LLM
        result = await asyncio.to_thread(client.call, messages)

        if result is None:
            _agent_status = {
                "running": False,
                "last_result": None,
                "error": "LLM call returned None",
            }
            return

        # Sauvegarde du signal
        signal = {
            "action": "HOLD",
            "confidence": "low",
            "reason": result.get("content", "")[:500],
            "crypto": crypto,
            "symbol": symbol,
            "live": live,
            "timestamp": time.time(),
            "model": result.get("model", "unknown"),
            "risk_check": risk_check,
        }

        # Parse l'action depuis la réponse LLM
        content = result.get("content", "").upper()
        if "BUY" in content:
            signal["action"] = "BUY"
            signal["confidence"] = "medium"
        elif "SELL" in content:
            signal["action"] = "SELL"
            signal["confidence"] = "medium"

        # Écrit le signal sur disque
        SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
        ts_str = time.strftime("%Y%m%d_%H%M%S")
        signal_file = SIGNALS_DIR / f"signal_{ts_str}.json"
        signal_file.write_text(json.dumps(signal, indent=2, ensure_ascii=False), encoding="utf-8")

        _agent_status = {
            "running": False,
            "last_result": signal,
            "error": None,
        }

    except Exception as e:
        _agent_status = {
            "running": False,
            "last_result": None,
            "error": str(e),
        }


# =========================================================
# ENDPOINTS
# =========================================================

@router.post("/run")
async def run_agent(req: AgentRunRequest, bg: BackgroundTasks):
    """Declenche un cycle agent en arriere-plan."""
    global _agent_task

    if _agent_status.get("running"):
        raise HTTPException(409, "Un cycle agent est deja en cours")

    async def _wrapped():
        await _run_agent_cycle(req.crypto, req.symbol, req.live)

    _agent_task = asyncio.create_task(_wrapped())
    return {
        "status":  "started",
        "crypto":  req.crypto,
        "symbol":  req.symbol,
        "live":    req.live,
    }


@router.get("/status")
def agent_status():
    """Statut du cycle agent en cours."""
    return _agent_status


@router.post("/stop")
async def stop_agent():
    """Arrête le cycle agent en cours."""
    global _agent_task
    if _agent_task and not _agent_task.done():
        _agent_task.cancel()
        _agent_status["running"] = False
        _agent_status["error"] = "Cancelled by user"
        return {"stopped": True}
    return {"stopped": False, "reason": "Pas de cycle actif"}


@router.get("/signals")
def get_all_signals(limit: int = 50):
    """Tous les signaux (trading + vision)."""
    if not SIGNALS_DIR.exists():
        return {"signals": []}

    # FIX ronde 8 : [-0:] renvoie la LISTE ENTIÈRE — limit=0 (et tout
    # limit <= 0) était un piège public ; même clamp que main.py:911.
    limit = max(1, min(int(limit), 100))
    all_files = sorted(SIGNALS_DIR.glob("*.json"))[-limit:]
    signals   = []
    for f in reversed(all_files):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_file"] = f.name
            signals.append(data)
        except Exception:
            pass
    return {"signals": signals, "count": len(signals)}


@router.get("/signals/stats")
def signal_stats():
    """Statistiques des signaux."""
    if not SIGNALS_DIR.exists():
        return {}

    total  = buy = sell = hold = 0
    for f in SIGNALS_DIR.glob("signal_*.json"):
        try:
            data   = json.loads(f.read_text(encoding="utf-8"))
            action = data.get("action", "HOLD")
            total += 1
            if action == "BUY":   buy  += 1
            elif action == "SELL": sell += 1
            else:                  hold += 1
        except Exception:
            pass

    return {
        "total": total,
        "buy":   buy,
        "sell":  sell,
        "hold":  hold,
        "buy_pct":  round(buy  / total * 100, 1) if total else 0,
        "sell_pct": round(sell / total * 100, 1) if total else 0,
    }
