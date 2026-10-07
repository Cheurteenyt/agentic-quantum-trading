"""
Router Vision — Gemini Flash pour analyse SMC
===============================================
Utilise Google Gemini Flash (gratuit, 1500 req/jour) pour analyser
les screenshots NinjaTrader 8 et detecter les setups SMC.

Gemini Flash a une vision excellente et peut lire les bougies,
identifier les Order Blocks, FVG, liquidity sweeps, etc.
"""

import base64
import asyncio
import json
import os
import re
import time   # PR-174 : utilisé aux lignes 623/690+, jamais importé
from pathlib import Path

import aiohttp
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class AgentInstruction(BaseModel):
    instruction: str
    max_steps: int = 10


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    print("[WARN] GEMINI_API_KEY not set in vision.py")
GEMINI_URL     = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

SIGNALS_DIR    = Path("data/signals")
SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR = Path("data/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# PROMPTS SMC
# =========================================================

SMC_BASE = """Tu es un expert en Smart Money Concepts (SMC) et Order Flow trading avec 10 ans d'experience.

Analyse ce chart de trading et identifie avec precision :

STRUCTURE DE MARCHE :
- Tendance dominante (bullish / bearish / range)
- BOS (Break of Structure) ou CHoCH (Change of Character) visibles
- Niveaux cles (highs/lows importants)

ORDER FLOW :
- Zones d'absorption visible (gros volumes sans mouvement de prix)
- Delta positif ou negatif dans les bougies recentes
- Imbalances de volume (gaps de volume)

SMART MONEY CONCEPTS :
- Order Blocks (OB) : derniere bougie avant mouvement fort
- Fair Value Gaps (FVG) : gaps de prix non combles entre bougies
- Liquidity Sweeps : cassure de high/low suivie d'un retournement
- Equal highs/lows (zones de liquidite)

SETUP TRADEABLE :
- Y a-t-il un setup confluence de plusieurs elements ?
- Direction suggeree (LONG/SHORT/NONE)
- Zone d'entree approximative
- Invalidation du setup

Reponds UNIQUEMENT en JSON valide avec cette structure exacte :
{
  "structure": {
    "trend": "bullish|bearish|range",
    "bos_choch": "description ou null",
    "key_levels": ["niveau1", "niveau2"]
  },
  "order_flow": {
    "absorption_detected": true,
    "delta_bias": "positive|negative|neutral",
    "imbalance_zones": ["description"]
  },
  "smc": {
    "order_blocks": ["description"],
    "fvg": ["description"],
    "liquidity_sweeps": ["description"],
    "liquidity_pools": ["description"]
  },
  "setup": {
    "has_setup": true,
    "direction": "LONG|SHORT|NONE",
    "entry_zone": "description",
    "invalidation": "description",
    "confidence": "low|medium|high",
    "reasoning": "justification en 2-3 phrases"
  }
}"""

XAUUSD_EXTRA = """
CONTEXT SPECIAL XAUUSD/GC (Or) :
- Marche tres volatile avec mouvements violents frequents
- Attention aux fakeouts sur niveaux ronds (ex: 4500, 4480)
- Les absorptions massives precedent souvent les reversals
- Les spikes de prix sont courants avant les retournements
"""

# =========================================================
# GEMINI CLIENT
# =========================================================

async def call_gemini(img_b64: str, instrument: str = "XAUUSD",
                      timeframe: str = "5m", notes: str = "") -> dict:
    """Envoie le screenshot a Gemini Flash pour analyse SMC."""

    extra   = XAUUSD_EXTRA if "XAU" in instrument.upper() or "GC" in instrument.upper() else ""
    prompt  = f"{SMC_BASE}{extra}\n\nINSTRUMENT: {instrument} | TIMEFRAME: {timeframe}"
    if notes:
        prompt += f"\n\nNOTES: {notes}"

    return await _gemini_request(img_b64, prompt)


async def call_gemini_custom(img_b64: str, prompt: str) -> dict:
    """Envoie le screenshot a Gemini Flash avec un prompt custom (pour agent mode)."""
    return await _gemini_request(img_b64, prompt)


async def _gemini_request(img_b64: str, prompt: str) -> dict:
    """Requête Gemini générique — image + texte → JSON."""
    payload = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data":      img_b64,
                    }
                },
                {
                    "text": prompt
                }
            ]
        }],
        "generationConfig": {
            "temperature":     0.1,
            "maxOutputTokens": 1000,
            "responseMimeType": "application/json",
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            GEMINI_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(resp.status, f"Gemini error: {text[:200]}")

            data = await resp.json()

    # Extrait le texte de la reponse
    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        # Nettoie les backticks si presents
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        return json.loads(raw)
    except (KeyError, json.JSONDecodeError) as e:
        # Essaie d'extraire un JSON du texte
        try:
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
        raise HTTPException(500, f"Parse error: {e} | raw: {str(data)[:300]}")


# =========================================================
# MODELS
# =========================================================

class AnalyzeRequest(BaseModel):
    screenshot_path: str = None
    instrument:      str = "XAUUSD"
    timeframe:       str = "5m"
    notes:           str = ""


# =========================================================
# ENDPOINTS
# =========================================================

@router.post("/analyze")
async def analyze_chart(req: AnalyzeRequest):
    """
    Screenshot + analyse SMC via Gemini Flash.
    """
    img_b64 = None

    # Charge l'image
    if req.screenshot_path:
        path = Path(req.screenshot_path)
        if path.exists():
            img_b64 = base64.b64encode(path.read_bytes()).decode()

    if not img_b64:
        # Prend un screenshot via windows-mcp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://localhost:8000/api/desktop/screenshot",
                    timeout=aiohttp.ClientTimeout(total=35),
                ) as r:
                    d = await r.json()
                    if d.get("success") and d.get("image"):
                        img_b64 = d["image"]
        except Exception as e:
            return {"error": f"Screenshot impossible: {e}"}

    if not img_b64:
        return {"error": "Aucune image disponible"}

    # Analyse via Gemini
    try:
        analysis = await call_gemini(
            img_b64,
            instrument=req.instrument,
            timeframe=req.timeframe,
            notes=req.notes,
        )
    except HTTPException:
        raise
    except Exception as e:
        return {"error": f"Gemini error: {e}"}

    # Sauvegarde
    ts     = int(time.time())
    result = {
        "ts":         ts,
        "instrument": req.instrument,
        "timeframe":  req.timeframe,
        "analysis":   analysis,
        "model":      "gemini-2.0-flash",
        "has_image":  True,
    }
    path = SIGNALS_DIR / f"vision_{ts}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


@router.get("/latest")
async def latest_analysis():
    """Retourne la derniere analyse vision."""
    files = sorted(SIGNALS_DIR.glob("vision_*.json"))
    if not files:
        raise HTTPException(404, "Aucune analyse")
    return json.loads(files[-1].read_text(encoding="utf-8"))


@router.get("/history")
async def analysis_history(limit: int = 10):
    """Historique des analyses."""
    files   = sorted(SIGNALS_DIR.glob("vision_*.json"))[-limit:]
    history = []
    for f in reversed(files):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            history.append({
                "ts":         d.get("ts"),
                "instrument": d.get("instrument"),
                "timeframe":  d.get("timeframe"),
                "direction":  d.get("analysis", {}).get("setup", {}).get("direction", "NONE"),
                "confidence": d.get("analysis", {}).get("setup", {}).get("confidence", "low"),
                "has_setup":  d.get("analysis", {}).get("setup", {}).get("has_setup", False),
                "model":      d.get("model", "unknown"),
            })
        except Exception:
            pass
    return {"history": history, "count": len(history)}


@router.post("/auto-scan")
async def auto_scan(instrument: str = "XAUUSD", timeframe: str = "5m"):
    """Screenshot automatique + analyse + sauvegarde si setup detecte."""
    req    = AnalyzeRequest(instrument=instrument, timeframe=timeframe)
    result = await analyze_chart(req)

    setup = result.get("analysis", {}).get("setup", {})
    if setup.get("has_setup") and setup.get("confidence") in ("medium", "high"):
        path = SIGNALS_DIR / f"smc_signal_{int(time.time())}.json"
        path.write_text(
            json.dumps({**result, "auto_generated": True}, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        result["signal_saved"] = True

    return result


@router.get("/test")
async def test_gemini():
    """Test la connexion Gemini avec une image simple."""
    # Image 1x1 pixel blanc en base64
    test_img = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFgABAQEAAAAAAAAAAAAAAAAABgUE/8QAIBAAAQQCAgMAAAAAAAAAAAAAAQIDBBEFEiExQf/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwq6q4rIVlvqJ0UjM98cjHMkaHtOi0ggg/YEEEAf/Z"
    try:
        payload = {
            "contents": [{"parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": test_img}},
                {"text": "Dis juste OK si tu vois cette image."}
            ]}],
            "generationConfig": {"maxOutputTokens": 10}
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(GEMINI_URL, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                d = await r.json()
                text = d["candidates"][0]["content"]["parts"][0]["text"]
                return {"status": "ok", "gemini_response": text, "model": "gemini-2.0-flash"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# =========================================================
# AGENT MODE — IA pilote dynamiquement NT8 via MCP
# =========================================================
# Gemini voit l'écran, décide de l'action MCP à faire,
# on l'exécute, on recommence — boucle jusqu'à done.
# Plus de coordonnées hardcodées, plus de phases fixes.
# =========================================================

MCP_TOOLS_DESCRIPTION = """
TOOLS DISPONIBLES (windows-mcp) — TU PEUX UTILISER N'IMPORTE LEQUEL :

1. Screenshot — Prend un screenshot de l'écran. Aucun paramètre.
   → Utilise-le pour voir l'état actuel de l'écran.

2. Snapshot — Extrait le texte de l'interface. Paramètres: {"use_vision": true, "use_dom": false}
   → IMPORTANT: use_dom=false car NT8 est une app native Windows, pas un navigateur.
   → Utilise-le pour lire les valeurs de la Data Box, les noms d'indicateurs, etc.

3. Click — Clique à des coordonnées. Paramètres: {"x": int, "y": int, "button": "left"|"right"|"middle"}
   → button "left" par défaut. Utilise "right" pour les menus contextuels.

4. Move — Déplace le curseur. Paramètres: {"x": int, "y": int}
   → Utilise pour survoler des éléments (ex: activer la Data Box sur une bougie).

5. Type — Tape du texte. Paramètres: {"text": "texte à taper"}
   → Pour rechercher un indicateur, changer un timeframe dans un dropdown, etc.

6. Shortcut — Appuie sur une touche ou combinaison. Paramètres: {"keys": "Enter"|"Escape"|"Ctrl+I"|"F5"|"Delete"|"ArrowUp"|"ArrowDown"}

7. Scroll — Scroll de la molette. Paramètres: {"x": int, "y": int, "direction": "up"|"down", "amount": int}

8. App — Lance ou switch d'app. Paramètres: {"action": "launch"|"switch", "name": "nom de l'app", "args": []}
   → Pour switcher sur NinjaTrader: {"action": "switch", "name": "NinjaTrader"}

9. Wait — Attendre. Paramètres: {"duration": nombre_de_secondes}

IMPORTANT — NT8 EST UNE APP NATIVE WINDOWS :
- Les fenêtres/dialogues ne sont pas des pages web
- Les menus contextuels apparaissent après un clic droit
- La Data Box s'affiche quand on survole une bougie
- Ctrl+I ouvre la fenêtre des indicateurs
- F5 rafraîchit le chart
- Le mot de passe de connexion doit être cliqué AVANT d'être tapé

CONVENTION DE COORDONNÉES :
- Écran 1920x1080 typique
- Le chart occupe le centre de l'écran
- Les dropdowns (timeframe, instrument) sont en haut
- Les indicateurs sont en bas ou sur les côtés
- SI TU NE VOIS PAS UN ÉLÉMENT : utilise Snapshot d'abord pour localiser le texte
"""

AGENT_LOOP_PROMPT = """Tu es un agent IA qui contrôle NinjaTrader 8 via des outils MCP.

TÂCHE DE L'UTILISATEUR : {instruction}

ÉTAT ACTUEL DE L'ÉCRAN : tu vois un screenshot ci-dessous.
HISTORIQUE DES ACTIONS PRÉCÉDENTES :
{history}

RÈGLES CRITIQUES :
1. Réfléchis d'abord : qu'est-ce que tu vois sur l'écran ? Qu'est-ce qui manque pour accomplir la tâche ?
2. Si NT8 n'est pas au premier plan, utilise App(switch, "NinjaTrader") d'abord.
3. Prends un Screenshot au début de chaque étape pour voir l'état actuel.
4. Après chaque action qui modifie l'UI (Click, Type, Shortcut), attends (Wait) avant de faire la prochaine action. NT8 a de la latence.
5. Pour ajouter un indicateur : clic droit sur le chart → clique sur "Indicators..." dans le menu → tape le nom → Enter → Enter.
6. Pour changer le timeframe : clique sur le dropdown timeframe → tape le nouveau tf → Enter.
7. Pour lire les valeurs (CVD, Delta, etc.) : Move sur une bougie → Snapshot(use_vision=true, use_dom=false).
8. Quand tu as TOUT ce qu'il faut pour produire le résultat final, retourne "done": true.

RÉPONDS UNIQUEMENT avec ce JSON :
{{
  "thought": "ce que je vois et ce que je vais faire ensuite",
  "action": {{
    "tool": "nom de l'outil MCP (Screenshot, Click, Move, Type, Shortcut, Snapshot, App, Wait, Scroll)",
    "params": {{paramètres pour l'outil}}
  }},
  "wait_after": 0.5,
  "done": false,
  "final_result": null
}}

SI LA TÂCHE EST TERMINÉE :
{{
  "thought": "résumé de ce qui a été fait",
  "action": null,
  "wait_after": 0,
  "done": true,
  "final_result": {{
    "smc_analysis": {{...analyse SMC complète au format habituel...}},
    "data_box_values": {{"cvd": "...", "delta": "...", "poc": "...", ...}},
    "signal": {{"direction": "LONG|SHORT|NONE", "confidence": "low|medium|high", "reasoning": "..."}}
  }}
}}
"""


def _mcp_call_sync(client, tool_name: str, params: dict, timeout: int = 30) -> dict:
    """Appel MCP synchrone avec gestion d'erreur."""
    try:
        result = client.call_tool(tool_name, params, timeout=timeout)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _mcp_screenshot_sync(client) -> tuple:
    """Screenshot MCP synchrone. Retourne (img_b64_or_None, filepath_or_None, info)."""
    try:
        result = client.call_tool("Screenshot", {}, timeout=30)
        content = result.get("result", {}).get("content", [])
        img_b64 = None
        info = ""
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "image":
                img_b64 = item.get("data", "")
            elif item.get("type") == "text":
                info = item.get("text", "")

        filepath = None
        if img_b64:
            ts = int(time.time())
            filepath = SCREENSHOTS_DIR / f"agent_{ts}.jpg"
            try:
                filepath.write_bytes(base64.b64decode(img_b64))
            except Exception:
                filepath = None

        return img_b64, str(filepath) if filepath else None, info
    except Exception as e:
        return None, None, str(e)


def _mcp_snapshot_sync(client) -> str:
    """Snapshot MCP synchrone. Retourne le texte extrait."""
    try:
        result = client.call_tool("Snapshot", {
            "use_vision": True,
            "use_dom": False,
        }, timeout=30)
        texts = []
        for item in result.get("result", {}).get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)
    except Exception:
        return ""


@router.post("/agent")
async def vision_agent(req: AgentInstruction):
    """
    Agent IA réel — Gemini voit l'écran, décide de l'action MCP,
    on l'exécute, on recommence. Boucle jusqu'à done ou max_steps.

    Plus de code hardcodé. L'IA contrôle dynamiquement NT8.
    """
    from routers.desktop import get_mcp

    client = get_mcp()
    if not client.connected:
        return {"error": "windows-mcp non connecte. Verifie que windows-mcp tourne sur Windows port 9000."}

    all_steps = []
    current_screenshot_b64 = None
    current_screenshot_path = None

    # ── Step 0 : Screenshot initial ──
    img_b64, img_path, img_info = await asyncio.to_thread(_mcp_screenshot_sync, client)
    if not img_b64:
        return {"error": "Screenshot initial échoué", "info": img_info}
    current_screenshot_b64 = img_b64
    current_screenshot_path = img_path
    all_steps.append({
        "step": 0,
        "type": "screenshot",
        "result": "capturé",
        "filepath": img_path,
    })

    action_history = []
    smc_result = None
    data_box_values = {}

    # ── Agent Loop ──
    for step_num in range(1, req.max_steps + 1):
        history_text = "\n".join(f"  Step {s['step']}: {s['type']} → {s.get('result', s.get('error', ''))}" for s in action_history[-8:])
        if not history_text:
            history_text = "  (aucune action précédente)"

        prompt = AGENT_LOOP_PROMPT.format(
            instruction=req.instruction,
            history=history_text,
        )

        # Ajoute SMC context à partir du step 4 pour forcer l'analyse finale
        if step_num >= max(4, req.max_steps - 2):
            prompt += "\n\nPRIORITÉ : si tu as les données nécessaires, termine maintenant avec done=true et produis l'analyse SMC complète + signal."

        # Envoie à Gemini
        try:
            decision = await call_gemini_custom(img_b64, prompt)
        except Exception as e:
            all_steps.append({
                "step": step_num,
                "type": "gemini_error",
                "error": str(e),
            })
            action_history.append({
                "step": step_num,
                "type": "gemini_error",
                "result": str(e),
            })
            # Un screenshot retry en cas d'erreur Gemini
            img_b64, img_path, _ = await asyncio.to_thread(_mcp_screenshot_sync, client)
            if img_b64:
                current_screenshot_b64 = img_b64
                current_screenshot_path = img_path
            continue

        thought = decision.get("thought", "")
        done = decision.get("done", False)
        action = decision.get("action")
        final_result = decision.get("final_result")
        wait_after = decision.get("wait_after", 0.5)

        # Capture le final_result si Gemini le fournit
        if final_result:
            if isinstance(final_result, dict):
                smc_result = final_result.get("smc_analysis", smc_result)
                data_box_values = final_result.get("data_box_values", data_box_values)

        # Done — on arrête la loop
        if done:
            all_steps.append({
                "step": step_num,
                "type": "done",
                "thought": thought,
                "final_result": final_result,
            })
            # Screenshot final
            img_b64, img_path, _ = await asyncio.to_thread(_mcp_screenshot_sync, client)
            if img_b64:
                current_screenshot_b64 = img_b64
                current_screenshot_path = img_path
            break

        # Pas d'action — Gemini n'a rien décidé, on break pour éviter loop infinie
        if not action or not action.get("tool"):
            all_steps.append({
                "step": step_num,
                "type": "no_action",
                "thought": thought,
            })
            break

        # Exécute l'action MCP
        tool_name = action["tool"]
        params = action.get("params", {})

        step_entry = {
            "step": step_num,
            "type": tool_name,
            "thought": thought,
            "params": params,
        }

        if tool_name == "Screenshot":
            img_b64, img_path, info = await asyncio.to_thread(_mcp_screenshot_sync, client)
            if img_b64:
                current_screenshot_b64 = img_b64
                current_screenshot_path = img_path
                step_entry["result"] = "capturé"
            else:
                step_entry["error"] = info or "échoué"
            await asyncio.sleep(wait_after)

        elif tool_name == "Snapshot":
            text = await asyncio.to_thread(_mcp_snapshot_sync, client)
            # Extrait les valeurs data box du snapshot
            for pattern, name in [
                (r"CVD[:\s=]+([-+]?\d[\d,]*\.?\d*)", "cvd"),
                (r"Delta[:\s=]+([-+]?\d[\d,]*\.?\d*)", "delta"),
                (r"POC[:\s=]+([\d,]*\.?\d+)", "poc"),
                (r"VAH[:\s=]+([\d,]*\.?\d+)", "vah"),
                (r"VAL[:\s=]+([\d,]*\.?\d+)", "val"),
                (r"Volume[:\s=]+([\d,]+)", "volume"),
                (r"Bid[:\s=]+([\d,]*\.?\d+)", "bid"),
                (r"Ask[:\s=]+([\d,]*\.?\d+)", "ask"),
                (r"Last[:\s=]+([\d,]*\.?\d+)", "last"),
            ]:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    data_box_values[name] = match.group(1)
            step_entry["result"] = f"extrait ({len(text)} chars)"
            step_entry["data_box_values"] = data_box_values
            time.sleep(wait_after)

        elif tool_name == "Wait":
            duration = params.get("duration", 1)
            await asyncio.sleep(duration)
            step_entry["result"] = f"attendu {duration}s"

        else:
            # Click, Move, Type, Shortcut, App, Scroll, etc.
            # PR-174 : result n'était JAMAIS assigné (NameError à chaque
            # tool générique) — l'exécution passe par l'appel générique
            result = await asyncio.to_thread(_mcp_call_sync, client,
                                             tool_name, params)
            if result.get("success") or result.get("error") is None:
                step_entry["result"] = "exécuté"
            else:
                step_entry["error"] = result.get("error", "échoué")
            await asyncio.sleep(wait_after)

            # Après une action qui modifie l'UI, screenshot automatique
            if tool_name in ("Click", "Type", "Shortcut", "App"):
                img_b64, img_path, _ = await asyncio.to_thread(_mcp_screenshot_sync, client)
                if img_b64:
                    current_screenshot_b64 = img_b64
                    current_screenshot_path = img_path
                    step_entry["screenshot_after"] = "capturé"

        all_steps.append(step_entry)
        action_history.append({
            "step": step_num,
            "type": tool_name,
            "result": step_entry.get("result", step_entry.get("error", "")),
        })

    # ── SMC Analysis finale si pas déjà fournie par Gemini ──
    if not smc_result and current_screenshot_b64:
        context_text = ""
        if data_box_values:
            context_text = f"\n\nVALEURS DATA BOX:\n{json.dumps(data_box_values, indent=2)}"
        if req.instruction:
            context_text += f"\n\nNOTES UTILISATEUR: {req.instruction}"

        try:
            smc_result = await call_gemini(
                current_screenshot_b64,
                instrument="XAUUSD",
                timeframe="5m",
                notes=context_text,
            )
        except Exception as e:
            smc_result = {"error": str(e)}

    # ── Construction du signal ──
    if isinstance(smc_result, dict):
        setup = smc_result.get("setup", {})
    else:
        setup = {}

    signal = {
        "direction": setup.get("direction", "NONE"),
        "confidence": setup.get("confidence", "low"),
        "has_setup": setup.get("has_setup", False),
        "entry_zone": setup.get("entry_zone", ""),
        "stop_loss": setup.get("stop_loss", ""),
        "take_profit": setup.get("take_profit", ""),
        "reasoning": setup.get("reasoning", ""),
        "data_box": data_box_values,
    }

    # ── Sauvegarde ──
    ts = int(time.time())
    result = {
        "success": True,
        "steps_taken": len(all_steps),
        "max_steps": req.max_steps,
        "instruction": req.instruction,
        "steps": all_steps,
        "signal": signal,
        "last_image": current_screenshot_b64,
        "last_image_path": current_screenshot_path,
        "smc_analysis": smc_result,
    }
    path = SIGNALS_DIR / f"agent_{ts}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


# =========================================================
# AUTO-SCAN
# =========================================================

import asyncio
_autoscan_task = None
_autoscan_running = False

@router.post("/autoscan/start")
async def start_autoscan(instrument: str = "XAUUSD", interval: int = 1800):
    """Lance l'auto-scan toutes les X secondes (defaut 30min)."""
    global _autoscan_task, _autoscan_running

    if _autoscan_running:
        return {"status": "already_running", "interval": interval}

    _autoscan_running = True

    async def _loop():
        while _autoscan_running:
            try:
                req = AnalyzeRequest(instrument=instrument, timeframe="5m")
                await analyze_chart(req)
            except Exception:
                pass
            await asyncio.sleep(interval)

    _autoscan_task = asyncio.create_task(_loop())
    return {"status": "started", "interval_min": interval // 60, "instrument": instrument}


@router.post("/autoscan/stop")
async def stop_autoscan():
    """Arrête l'auto-scan."""
    global _autoscan_running, _autoscan_task
    _autoscan_running = False
    if _autoscan_task:
        _autoscan_task.cancel()
        _autoscan_task = None
    return {"status": "stopped"}


@router.get("/autoscan/status")
async def autoscan_status():
    """Statut de l'auto-scan."""
    return {"running": _autoscan_running}
