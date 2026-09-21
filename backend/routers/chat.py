"""
Router Chat — Pont Dashboard ↔ Hermes Agent
============================================
Lance hermes chat -q en subprocess et retourne la reponse.
"""

import asyncio
import json
import re
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

HERMES_DIR  = Path("/mnt/d/hermes-agent-main")
HERMES_VENV = HERMES_DIR / ".venv/bin/hermes"
HISTORY_DIR = Path("data/chat")
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# MODELS
# =========================================================

class ChatRequest(BaseModel):
    message: str
    session_id: str = None

class ChatResponse(BaseModel):
    response:   str
    session_id: str
    model:      str = "Qwen3.5-9B"
    ts:         float = None

# =========================================================
# HERMES BRIDGE
# =========================================================

async def call_hermes(message: str, session_id: str = None) -> dict:
    """Lance hermes chat -q en subprocess et capture la reponse."""

    cmd = [
        str(HERMES_VENV),
        "chat",
        "-q", message,
        "-Q",
        "-t", "web,terminal,file",
    ]

    if session_id:
        cmd += ["--resume", session_id]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(HERMES_DIR),
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=120
        )

        output = stdout.decode("utf-8", errors="replace").strip()
        error  = stderr.decode("utf-8", errors="replace").strip()

        # Extrait session_id de la sortie
        new_session_id = session_id
        sid_match = re.search(r"session_id:\s*(\S+)", output)
        if sid_match:
            new_session_id = sid_match.group(1)
            # Retire la ligne session_id de la reponse
            output = re.sub(r"\nsession_id:\s*\S+", "", output).strip()

        if proc.returncode != 0 and not output:
            return {
                "response":   f"Erreur Hermes: {error[:200] or 'timeout'}",
                "session_id": session_id or "",
                "model":      "error",
            }

        return {
            "response":   output or "...",
            "session_id": new_session_id or "",
            "model":      "Qwen3.5-9B-local",
        }

    except asyncio.TimeoutError:
        return {
            "response":   "Timeout — le modèle local prend trop de temps. Réessaie.",
            "session_id": session_id or "",
            "model":      "timeout",
        }
    except Exception as e:
        return {
            "response":   f"Erreur: {e}",
            "session_id": session_id or "",
            "model":      "error",
        }

# =========================================================
# ENDPOINTS
# =========================================================

@router.post("/message")
async def send_message(req: ChatRequest):
    """Envoie un message a Hermes et retourne la reponse."""
    ts     = time.time()
    result = await call_hermes(req.message, req.session_id)

    # Sauvegarde historique
    log = {
        "ts":         ts,
        "user":       req.message,
        "hermes":     result["response"],
        "session_id": result["session_id"],
        "model":      result["model"],
    }
    log_file = HISTORY_DIR / f"chat_{int(ts)}.json"
    log_file.write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")

    return {
        **result,
        "ts": ts,
    }


@router.get("/history")
async def get_history(limit: int = 20):
    """Retourne l'historique des conversations."""
    files = sorted(HISTORY_DIR.glob("chat_*.json"))[-limit:]
    history = []
    for f in reversed(files):
        try:
            history.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return {"history": history, "count": len(history)}


@router.get("/status")
async def chat_status():
    """Verifie que Hermes est accessible."""
    try:
        proc = await asyncio.create_subprocess_exec(
            str(HERMES_VENV), "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        version = stdout.decode().strip()
        return {
            "status":      "ok",
            "hermes":      version,
            "model":       "Qwen3.5-9B-local",
            "hermes_path": str(HERMES_VENV),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.delete("/history")
async def clear_history():
    """Efface l'historique."""
    for f in HISTORY_DIR.glob("chat_*.json"):
        f.unlink()
    return {"cleared": True}
