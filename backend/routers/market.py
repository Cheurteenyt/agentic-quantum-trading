"""
Router Market — données MT5 + Hyperliquid
"""
import json
import time
from pathlib import Path

import aiohttp
from fastapi import APIRouter, HTTPException

router   = APIRouter()
MT5_URL  = "http://host.docker.internal:8765"
SNAP_DIR = Path("data/snapshots")


async def mt5_get(path: str) -> dict:
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=3)
    ) as s:
        async with s.get(f"{MT5_URL}{path}") as r:
            return await r.json()


@router.get("/snapshot/{coin}")
async def get_snapshot(coin: str):
    path = SNAP_DIR / f"{coin.lower()}_latest.json"
    if not path.exists():
        raise HTTPException(404, f"Pas de snapshot pour {coin}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["age_sec"] = round(time.time() - data.get("ts", 0), 1)
    return data


@router.get("/snapshots")
async def get_all_snapshots():
    result = {}
    for f in SNAP_DIR.glob("*_latest.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            coin = data.get("coin", f.stem.replace("_latest", "").upper())
            data["age_sec"] = round(time.time() - data.get("ts", 0), 1)
            result[coin] = data
        except Exception:
            pass
    return result


@router.get("/mt5/price/{symbol}")
async def get_price(symbol: str):
    try:
        return await mt5_get(f"/price/{symbol}")
    except Exception as e:
        raise HTTPException(503, f"MT5 Bridge indisponible: {e}")


@router.get("/mt5/account")
async def get_account():
    try:
        return await mt5_get("/account")
    except Exception as e:
        raise HTTPException(503, str(e))


@router.get("/mt5/positions")
async def get_positions():
    try:
        return await mt5_get("/positions")
    except Exception as e:
        raise HTTPException(503, str(e))


@router.get("/mt5/symbols")
async def get_symbols():
    try:
        return await mt5_get("/symbols")
    except Exception as e:
        raise HTTPException(503, str(e))


@router.get("/mt5/health")
async def mt5_health():
    try:
        return await mt5_get("/health")
    except Exception:
        return {"status": "disconnected", "mt5_available": False}


@router.get("/signals")
async def get_signals(limit: int = 20):
    signals_dir = Path("data/signals")
    if not signals_dir.exists():
        return {"signals": []}
    files = sorted(signals_dir.glob("signal_*.json"))[-limit:]
    signals = []
    for f in reversed(files):
        try:
            signals.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return {"signals": signals, "count": len(signals)}


# =========================================================
# NINJATRADER DATA RECEIVER
# =========================================================

_nt8_data = {}

@router.post("/ninjatrader")
async def receive_ninjatrader_data(data: dict):
    """Reçoit les données exportées par HermesDataExporter.cs"""
    global _nt8_data
    _nt8_data = {**data, "received_at": time.time()}
    return {"status": "ok", "ts": _nt8_data.get("ts")}

@router.get("/ninjatrader")
async def get_ninjatrader_data():
    """Retourne les dernières données NT8."""
    if not _nt8_data:
        return {"status": "no_data", "message": "HermesDataExporter pas encore connecté"}
    return _nt8_data
