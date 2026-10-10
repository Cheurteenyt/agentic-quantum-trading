"""
Router Desktop — windows-mcp
=============================
Utilise windows-mcp (port 9000 Windows) pour :
  - Screenshots via Screenshot tool
  - Lancement d'apps via App tool
  - Controle souris/clavier via Click/Type/Shortcut tools
  - NinjaTrader 8 launch

windows-mcp tourne sur Windows, accessible depuis WSL via host.docker.internal:9000
Le protocole MCP SSE requiert un handshake initialize avant les appels.
"""

import base64
import asyncio
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

WINDOWS_MCP_URL = "http://host.docker.internal:9000"
SCREENSHOTS_DIR = Path("data/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# NT8 password from env var (not hardcoded)
NT8_PASSWORD = os.getenv("NT8_PASSWORD", "")
if not NT8_PASSWORD:
    print("[WARN] NT8_PASSWORD not set in desktop.py - login will fail without manual input")

# =========================================================
# MODELS
# =========================================================

class MouseClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"

class KeyboardRequest(BaseModel):
    keys:  Optional[str] = None
    text:  Optional[str] = None

class AppLaunchRequest(BaseModel):
    app:  str
    args: list[str] = []

# =========================================================
# CLIENT WINDOWS-MCP (SSE + MCP protocol)
# =========================================================

class _MCPClient:
    """Client MCP SSE persistant — garde le stream ouvert."""

    def __init__(self, base_url: str):
        self.base_url  = base_url
        self.msg_url   = None
        self.connected = False
        self._resp     = {}
        self._lock     = threading.Lock()
        self._thread   = None

    def connect(self, timeout: int = 10) -> bool:
        if self.connected and self.msg_url:
            return True
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.connected:
                break
            time.sleep(0.05)
        if not self.connected:
            return False
        self._init_handshake()
        return True

    def _read(self):
        try:
            r = requests.get(
                f"{self.base_url}/sse", stream=True, timeout=(5, None)
            )
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if "session_id" in data and not self.connected:
                        sid = data.split("session_id=")[-1]
                        self.msg_url   = f"{self.base_url}/messages/?session_id={sid}"
                        self.connected = True
                    elif data and data.startswith("{"):
                        try:
                            msg = json.loads(data)
                            mid = str(msg.get("id", ""))
                            if mid:
                                with self._lock:
                                    self._resp[mid] = msg
                        except Exception:
                            pass
        except Exception:
            self.connected = False

    def _init_handshake(self):
        mid = "init_" + str(uuid.uuid4())[:8]
        self._post_wait(mid, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities":    {},
            "clientInfo":      {"name": "hermes", "version": "1.0"},
        }, timeout=5)
        requests.post(self.msg_url, json={
            "jsonrpc": "2.0", "id": "notif",
            "method":  "notifications/initialized", "params": {},
        }, timeout=5)
        time.sleep(0.2)

    def _post_wait(self, mid: str, method: str, params: dict,
                   timeout: int = 30) -> dict:
        try:
            requests.post(self.msg_url, json={
                "jsonrpc": "2.0", "id": mid,
                "method":  method, "params": params,
            }, timeout=10)
        except Exception as e:
            return {"error": str(e)}

        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if mid in self._resp:
                    return self._resp.pop(mid)
            time.sleep(0.05)
        return {"error": f"Timeout {timeout}s"}

    def call_tool(self, name: str, arguments: dict = {},
                  timeout: int = 30) -> dict:
        if not self.connected:
            if not self.connect():
                return {"error": "windows-mcp non connecte"}
        mid = str(uuid.uuid4())[:12]
        return self._post_wait(
            mid, "tools/call",
            {"name": name, "arguments": arguments},
            timeout=timeout,
        )

    def list_tools(self) -> list:
        if not self.connected:
            if not self.connect():
                return []
        mid    = str(uuid.uuid4())[:12]
        result = self._post_wait(mid, "tools/list", {}, timeout=10)
        return result.get("result", {}).get("tools", [])


_client: _MCPClient | None = None
_client_lock = threading.Lock()


def get_mcp() -> _MCPClient:
    global _client
    with _client_lock:
        if _client is None or not _client.connected:
            _client = _MCPClient(WINDOWS_MCP_URL)
            _client.connect(timeout=10)
    return _client


def mcp_screenshot() -> dict:
    """Screenshot via windows-mcp, retourne base64 + filepath."""
    client  = get_mcp()
    result  = client.call_tool("Screenshot", {}, timeout=30)
    content = result.get("result", {}).get("content", [])
    img_b64 = None
    info    = ""

    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "image":
            img_b64 = item.get("data", "")
        elif item.get("type") == "text":
            info = item.get("text", "")

    filepath = None
    if img_b64:
        ts       = int(time.time())
        filepath = SCREENSHOTS_DIR / f"screen_{ts}.jpg"
        try:
            filepath.write_bytes(base64.b64decode(img_b64))
        except Exception:
            filepath = None

    return {
        "success":  img_b64 is not None,
        "image":    img_b64,
        "format":   "jpeg",
        "filepath": str(filepath) if filepath else None,
        "info":     info[:200],
        "ts":       time.time(),
    }

# =========================================================
# ENDPOINTS
# =========================================================

@router.get("/status")
def desktop_status():
    """Statut du client windows-mcp."""
    try:
        client = get_mcp()
        tools  = client.list_tools() if client.connected else []
        return {
            "windows_mcp":    client.connected,
            "mcp_url":        WINDOWS_MCP_URL,
            "tools_count":    len(tools),
            "tools":          [t.get("name") if isinstance(t, dict) else t for t in tools],
            "screenshots_dir": str(SCREENSHOTS_DIR.resolve()),
        }
    except Exception as e:
        return {
            "windows_mcp":  False,
            "error":        str(e),
            "mcp_url":      WINDOWS_MCP_URL,
        }


@router.post("/screenshot")
async def take_screenshot():
    """Prend un screenshot via windows-mcp."""
    try:
        result = mcp_screenshot()
        if not result["success"]:
            raise HTTPException(500, "Screenshot echoue")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/screenshots")
async def list_screenshots(limit: int = 10):
    """Liste les derniers screenshots."""
    # R9 : clamp — limit=0 => [-0:] renvoyait la LISTE ENTIÈRE (tous les
    # .jpg chargés), limit négatif inversait le sens du slice (même pattern
    # corrigé dans intel.py / market.py — celui-ci avait été manqué).
    limit = max(1, min(int(limit), 100))
    files  = sorted(SCREENSHOTS_DIR.glob("*.jpg"))[-limit:]
    result = []
    for f in reversed(files):
        result.append({
            "name": f.name,
            "path": str(f),
            "ts":   f.stat().st_mtime,
            "size": f.stat().st_size,
        })
    return {"screenshots": result}


@router.get("/screenshots/latest")
async def latest_screenshot():
    """Retourne le dernier screenshot en base64."""
    files = sorted(SCREENSHOTS_DIR.glob("*.jpg"))
    if not files:
        raise HTTPException(404, "Aucun screenshot")
    latest  = files[-1]
    img_b64 = base64.b64encode(latest.read_bytes()).decode()
    return {
        "image":  img_b64,
        "format": "jpeg",
        "name":   latest.name,
        "ts":     latest.stat().st_mtime,
    }


@router.post("/mouse/click")
async def mouse_click(req: MouseClickRequest):
    """Clique a une position via windows-mcp."""
    client = get_mcp()
    result = client.call_tool("Click", {
        "coordinates": [req.x, req.y],
        "button":       req.button,
    })
    return {"success": not result.get("error"), "result": result}


@router.post("/keyboard")
async def keyboard_input(req: KeyboardRequest):
    """Tape du texte ou envoie un raccourci clavier."""
    client = get_mcp()
    if req.text:
        result = client.call_tool("Type", {"text": req.text})
    else:
        result = client.call_tool("Shortcut", {"keys": req.keys})
    return {"success": not result.get("error"), "result": result}


@router.post("/launch/ninjatrader")
async def launch_ninjatrader():
    """Lance NinjaTrader 8 via windows-mcp App tool."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte — lance: uvx windows-mcp --transport sse --host 0.0.0.0 --port 9000")

    # Note: le chemin peut varier selon l'installation (Program Files, Documents, etc.)
    # Si ce chemin ne fonctionne pas, ajuster selon la réelle installation NT8
    nt8_path = r"D:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe"

    result = client.call_tool("App", {
        "mode": "launch",
        "name": nt8_path,
    })

    content = result.get("result", {}).get("content", [])
    text    = content[0].get("text", "") if content else ""
    success = not result.get("result", {}).get("isError", True)

    return {
        "success": success,
        "message": text,
        "nt8_path": nt8_path,
        "result":  result,
    }


class LaunchFullRequest(BaseModel):
    # ronde 11 : le password passait en QUERY PARAM (?password=…) — fuite
    # dans les access-logs uvicorn/proxy. Le body est le canal du pair
    # nt8_login (LoginRequest), même contrat ici.
    password: str = ""


@router.post("/launch/ninjatrader/full")
async def launch_ninjatrider_full(req: LaunchFullRequest):
    """
    Launcher complet NT8 : lance l'app, attend, clique le champ mot de passe, tape le mdp, Enter.
    Si aucun password fourni, utilise la variable d'environnement NT8_PASSWORD.
    """
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    # Use provided password or fallback to env var
    pwd_to_use = req.password or NT8_PASSWORD
    if not pwd_to_use:
        return {"error": "NT8_PASSWORD not set in environment and no password provided"}

    nt8_path = r"D:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe"

    # Étape 1 : Lancer NT8
    result = client.call_tool("App", {
        "mode": "launch",
        "name": nt8_path,
    })
    time.sleep(2)

    # Étape 2 : Screenshot pour voir la fenêtre de login
    ss1 = mcp_screenshot()

    # Étape 3 : Cliquer dans le champ password (coordonnées par défaut)
    client.call_tool("Move", {"x": 960, "y": 540})
    time.sleep(0.3)
    r_click = client.call_tool("Click", {"coordinates": [960, 540], "button": "left"})
    time.sleep(0.5)

    # Étape 4 : Taper le mot de passe
    r_type = client.call_tool("Type", {"text": pwd_to_use})
    await asyncio.sleep(0.3)

    # Étape 5 : Enter pour se connecter
    r_enter = client.call_tool("Shortcut", {"keys": "Enter"})
    await asyncio.sleep(3)

    # Étape 6 : Screenshot après connexion
    ss2 = mcp_screenshot()

    return {
        "success": _tool_ok(result, r_click, r_type, r_enter, ss2),
        "message": f"NT8 lancé et connecté automatiquement",
        "before_login_image": ss1.get("image"),
        "after_login_image": ss2.get("image"),
        "nt8_path": nt8_path,
    }


@router.post("/launch/app")
async def launch_app(req: AppLaunchRequest):
    """Lance une application Windows."""
    client = get_mcp()
    result = client.call_tool("App", {"mode": "launch", "name": req.app})
    return result


@router.post("/screenshot/analyze")
async def screenshot_and_analyze():
    """Screenshot + retourne l'image pour analyse vision."""
    result = mcp_screenshot()
    return result


@router.get("/tools")
async def list_tools():
    """Liste les outils windows-mcp disponibles."""
    client = get_mcp()
    tools  = client.list_tools()
    return {
        "tools": [
            {"name": t.get("name"), "description": t.get("description", "")[:100]}
            if isinstance(t, dict) else {"name": t}
            for t in tools
        ],
        "count": len(tools),
    }


# =========================================================
# NINJATRADER 8 — INDICATORS
# =========================================================

class IndicatorRequest(BaseModel):
    indicator: str   # "cvd", "volume_profile", "fof_aggression", "heatmap"
    action:    str   = "add"  # "add" | "remove"

class MoveRequest(BaseModel):
    x: int
    y: int

class ResizeRequest(BaseModel):
    name:   str = "NinjaTrader"
    width:  int = 1920
    height: int = 1080
    x_pos:  int = 0
    y_pos:  int = 0

class TimeframeRequest(BaseModel):
    timeframe: str  # "1m", "3m", "5m", "15m", "1H", "4H", "1D"

class LoginRequest(BaseModel):
    password: str = ""

class AgentInstruction(BaseModel):
    instruction: str  # ex: "met NT8 au premier plan, change le timeframe en 5m et fais une analyse SMC"
    max_steps: int = 10

# Mapping nom interne → nom exact dans NT8 (indicateurs NLambda sans erreurs)
NT8_INDICATORS = {
    # Indicateurs NTLambda Core
    "cvd": "NTLCVD",
    "volume_profile": "NTLVolumeProfile",
    "fof_aggression": "AggressionDelta",
    "fof_market_depth": "MarketDepth",
    "mark_important_levels": "MarkImportantLevels",
    "fof_vwap": "NTLVWAP",
    "fof_twap": "NTLTWAP",
    "ofi": "OFI",
    "cofi": "NTLCOFI",
    "tpo": "TPOIndicator",
    "session_probability": "SessionProbabilityOverlay",
    "moldy_bars": "MoldyBars",
    
    # DrawingTools
    "anchored_vwap": "NTLAnchoredVwap",
    "range_volume_profile": "NTLRangeVolumeProfile",
    
    # OrderFlowKit (doit être dans dossier Indicators principal)
    "bookmap": "Bookmap",
    "order_flow": "OrderFlow",
    "market_volume": "MarketVolume",
    "volume_analysis_profile": "VolumeAnalysisProfile",
    "volume_filter": "VolumeFilter",
    
    # ChartStyles
    "simple_high_low": "NTLSimpleHighLowChart",
    
    # AddOns ( Wyckoff, SE )
    "wyckoff_render": "WyckoffRender",
    "smart_engine": "SE",
}

# Coordonnées par défaut du centre du chart (ajustable via snapshot)
CHART_DEFAULT = {"x": 960, "y": 540}


def _tool_ok(*results) -> bool:
    """Le succès se DÉRIVE des results MCP, il ne se déclare pas.

    Ronde 11 : 8 handlers renvoyaient « success: True » codé dur — une
    action ratée (Timeout 30s, isError MCP) était rapportée comme réussie
    au frontend. mouse_click/keyboard_input dérivaient déjà du result :
    cette convention est étendue aux autres handlers."""
    for r in results:
        if not isinstance(r, dict):
            return False
        if r.get("error"):
            return False
        inner = r.get("result")
        if isinstance(inner, dict) and inner.get("isError"):
            return False
    return True


def _nt8_add_indicator(client: _MCPClient, indicator_name: str) -> dict:
    """
    Ajoute un indicateur dans NT8 via windows-mcp.
    Protocole :
      1. Clic droit sur le chart
      2. Clique "Indicators..."
      3. Tape le nom de l'indicateur
      4. Attend le chargement
      5. Clique OK
    """
    cx, cy = CHART_DEFAULT["x"], CHART_DEFAULT["y"]

    # 1. Clic droit sur le chart
    r1 = client.call_tool("Click", {
        "coordinates": [cx, cy],
        "button": "right",
    })
    time.sleep(0.8)

    # 2. Clique sur "Indicators..." dans le menu contextuel
    # Position par défaut : ~100px sous le clic, aligné gauche
    r2 = client.call_tool("Click", {
        "coordinates": [cx - 200, cy + 100],
        "button": "left",
    })
    time.sleep(0.8)

    # 3. Tape le nom de l'indicateur dans le champ de recherche
    r3 = client.call_tool("Type", {"text": indicator_name})
    time.sleep(0.5)

    # 4. Clique sur le premier résultat (Enter = sélection + ajout dans NT8)
    r4 = client.call_tool("Shortcut", {"keys": "Enter"})
    time.sleep(0.5)

    # 5. Clique OK pour confirmer
    r5 = client.call_tool("Shortcut", {"keys": "Enter"})
    time.sleep(0.5)

    return {"success": _tool_ok(r1, r2, r3, r4, r5),
            "indicator": indicator_name, "action": "add"}


def _nt8_remove_indicator(client: _MCPClient, indicator_name: str) -> dict:
    """
    Retire un indicateur de NT8.
    Protocole :
      1. Ctrl+I pour ouvrir la fenêtre Indicators
      2. Cherche l'indicateur
      3. Delete pour le retirer
      4. OK pour confirmer
    """
    # Ctrl+I ouvre la fenêtre des indicateurs
    r1 = client.call_tool("Shortcut", {"keys": "Ctrl+I"})
    time.sleep(0.8)

    # Tape le nom pour filtrer
    r2 = client.call_tool("Type", {"text": indicator_name})
    time.sleep(0.5)

    # Supprime l'indicateur sélectionné
    r3 = client.call_tool("Shortcut", {"keys": "Delete"})
    time.sleep(0.3)

    # Confirme
    r4 = client.call_tool("Shortcut", {"keys": "Enter"})
    time.sleep(0.3)

    return {"success": _tool_ok(r1, r2, r3, r4),
            "indicator": indicator_name, "action": "remove"}


@router.post("/ninjatrader/indicator")
async def nt8_indicator(req: IndicatorRequest):
    """Ajoute ou retire un indicateur dans NinjaTrader 8."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    nt8_name = NT8_INDICATORS.get(req.indicator)
    if not nt8_name:
        return {"error": f"Indicateur inconnu: {req.indicator}. Disponibles: {list(NT8_INDICATORS.keys())}"}

    if req.action == "remove":
        result = _nt8_remove_indicator(client, nt8_name)
    else:
        result = _nt8_add_indicator(client, nt8_name)

    return result


@router.post("/ninjatrader/switch")
async def nt8_switch():
    """Met NinjaTrader 8 en premier plan."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    result = client.call_tool("App", {
        "mode": "switch",
        "name": "NinjaTrader",
    })
    return {
        "success": not result.get("result", {}).get("isError", True),
        "result": result,
    }


@router.post("/ninjatrader/snapshot")
async def nt8_snapshot():
    """Snapshot complet NT8 avec extraction texte UI (valeurs indicateurs)."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    result = client.call_tool("Snapshot", {
        "use_vision": True,
        "use_dom":    False,  # apps natives comme NT8
    }, timeout=30)

    content = result.get("result", {}).get("content", [])
    text_data = ""
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text_data += item.get("text", "")

    return {
        "success": _tool_ok(result),
        "ui_text": text_data[:5000],  # Tronqué pour éviter payload trop gros
        "raw": result,
    }


@router.post("/ninjatrader/refresh")
async def nt8_refresh():
    """Rafraîchit le chart NT8 (F5)."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    r = client.call_tool("Shortcut", {"keys": "F5"})
    time.sleep(0.5)
    return {"success": _tool_ok(r), "action": "refresh"}


@router.post("/ninjatrader/zoom")
async def nt8_zoom(direction: str = "in", amount: int = 3):
    """Zoom in/out sur le chart NT8."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    cx, cy = CHART_DEFAULT["x"], CHART_DEFAULT["y"]
    if direction == "in":
        r = client.call_tool("Scroll", {
            "x": cx, "y": cy, "direction": "up", "amount": amount,
        })
    else:
        r = client.call_tool("Scroll", {
            "x": cx, "y": cy, "direction": "down", "amount": amount,
        })
    return {"success": _tool_ok(r), "action": f"zoom_{direction}", "amount": amount}


@router.post("/ninjatrader/login")
async def nt8_login(req: LoginRequest):
    """Connecte automatiquement NT8 après lancement (voit l'écran, clique password, entre mdp)."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    if not req.password:
        return {"error": "Mot de passe requis"}

    # Étape 1: Screenshot pour voir l'écran
    before_ss = mcp_screenshot()

    # Étape 2: Cliquer sur le champ password
    # Position typique de la fenêtre de login NT8 (centre écran)
    # À ajuster si la fenêtre est décalée
    pwd_x = 960   # centre horizontal
    pwd_y = 540   # centre vertical (zone du champ password)

    client.call_tool("Move", {"x": pwd_x, "y": pwd_y})
    time.sleep(0.3)
    r_click = client.call_tool("Click", {"coordinates": [pwd_x, pwd_y], "button": "left"})
    time.sleep(0.5)

    # Étape 3: Taper le mot de passe
    r_type = client.call_tool("Type", {"text": req.password})
    time.sleep(0.3)

    # Étape 4: Enter pour se connecter
    r_enter = client.call_tool("Shortcut", {"keys": "Enter"})
    time.sleep(3)

    # Étape 5: Screenshot après connexion pour confirmer
    after_ss = mcp_screenshot()

    return {
        "success": _tool_ok(r_click, r_type, r_enter, after_ss),
        "message": f"Login envoyé — click({pwd_x},{pwd_y}) → type(password) → Enter",
        "before_image": before_ss.get("image"),
        "after_image": after_ss.get("image"),
        "clicked_coords": {"x": pwd_x, "y": pwd_y},
    }


@router.post("/ninjatrader/move")
async def nt8_move(req: MoveRequest):
    """Déplace la souris sur le chart (hover pour lire valeurs)."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    result = client.call_tool("Move", {"x": req.x, "y": req.y})
    return {"success": not result.get("error"), "x": req.x, "y": req.y}


@router.post("/ninjatrader/resize")
async def nt8_resize(req: ResizeRequest):
    """Redimensionne la fenêtre NT8."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    result = client.call_tool("App", {
        "mode":   "resize",
        "name":   req.name,
        "width":  req.width,
        "height": req.height,
        "x":      req.x_pos,
        "y":      req.y_pos,
    })
    return {"success": not result.get("result", {}).get("isError", True)}


@router.post("/ninjatrader/timeframe")
async def nt8_timeframe(req: TimeframeRequest):
    """Change le timeframe du chart NT8 via clic sur la dropdown."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    cx, cy = CHART_DEFAULT["x"], CHART_DEFAULT["y"]

    # Coordonnées approximatives de la dropdown timeframe (haut gauche du chart)
    # À ajuster selon la config NT8
    tf_dropdown_x = cx - 350
    tf_dropdown_y = cy - 280

    # 1. Clic sur la dropdown timeframe
    client.call_tool("Click", {
        "coordinates": [tf_dropdown_x, tf_dropdown_y],
        "button": "left",
    })
    time.sleep(0.8)

    # 2. Tape le timeframe dans le champ de recherche
    client.call_tool("Type", {"text": req.timeframe})
    time.sleep(0.3)

    # 3. Enter pour confirmer
    client.call_tool("Shortcut", {"keys": "Enter"})
    time.sleep(0.5)

    # 4. Screenshot pour confirmer
    result = mcp_screenshot()

    return {
        "success": _tool_ok(result),
        "timeframe": req.timeframe,
        "image": result.get("image"),
    }


@router.get("/ninjatrader/data-box")
async def nt8_data_box():
    """Lit les valeurs actuelles de la Data Box NT8 (CVD, Delta, POC, VAH, VAL)."""
    client = get_mcp()
    if not client.connected:
        raise HTTPException(503, "windows-mcp non connecte")

    # Snapshot avec extraction texte UI
    result = client.call_tool("Snapshot", {
        "use_vision": True,
        "use_dom":    False,
    }, timeout=30)

    content = result.get("result", {}).get("content", [])
    ui_text = ""
    elements = []
    for item in content:
        if isinstance(item, dict):
            if item.get("type") == "text":
                ui_text += item.get("text", "")
            elif item.get("type") == "element":
                elements.append(item)

    # Parse les valeurs SMC/Order Flow du texte extrait
    parsed = {
        "raw_text": ui_text[:3000],
        "indicators": {},
    }

    # Recherche de patterns typiques NT8
    import re
    for pattern, name in [
        (r"CVD[:\s]+([-\d.]+)", "cvd"),
        (r"Delta[:\s]+([-\d.]+)", "delta"),
        (r"POC[:\s]+([\d.]+)", "poc"),
        (r"VAH[:\s]+([\d.]+)", "vah"),
        (r"VAL[:\s]+([\d.]+)", "val"),
        (r"Bid[:\s]+([\d.]+)", "bid"),
        (r"Ask[:\s]+([\d.]+)", "ask"),
        (r"Last[:\s]+([\d.]+)", "last"),
    ]:
        match = re.search(pattern, ui_text)
        if match:
            parsed["indicators"][name] = match.group(1)

    return {
        "success": _tool_ok(result),
        "data": parsed,
        "element_count": len(elements),
    }