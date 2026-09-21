"""
Router News — Analyse Gold via Firecrawl
==========================================
Scrape et analyse les donnees fondamentales XAUUSD :
  - COT Report (Commitments of Traders)
  - Drivers macro (FOMC, CPI, PPI, geopolitique)
  - Sentiment marche (retail + institutionnel)
  - Niveaux techniques et order flow
  - Forecasts analystes

Utilise Firecrawl pour scraper les meilleures sources financieres
et Gemini Flash pour structurer et synthetiser les donnees.
"""

import json
import os
import time
from pathlib import Path

import aiohttp
from fastapi import APIRouter, HTTPException
from firecrawl import Firecrawl

router = APIRouter()

FIRECRAWL_KEY = os.getenv("FIRECRAWL_API_KEY", "")
GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")
if not FIRECRAWL_KEY:
    print("[WARN] FIRECRAWL_API_KEY not set")
if not GEMINI_KEY:
    print("[WARN] GEMINI_API_KEY not set")
GEMINI_URL    = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

NEWS_DIR = Path("data/news")
NEWS_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# SOURCES A SCRAPER
# =========================================================

GOLD_SOURCES = [
    "https://www.kitco.com/gold-price-today-usa/",
    "https://www.fxstreet.com/rates-charts/gold",
    "https://www.investing.com/commodities/gold-news",
    "https://www.forexfactory.com/news",
]

COT_SOURCES = [
    "https://www.cftc.gov/dea/futures/deacmxlf.htm",
    "https://cotpricecharts.com/gold/",
]

# =========================================================
# PROMPT D'ANALYSE
# =========================================================

GOLD_ANALYSIS_PROMPT = """Tu es un analyste macro et order flow expert specialise sur l'Or (XAUUSD/GC Futures).

A partir des donnees scraped ci-dessous, construis une analyse complete et structuree.

DONNEES SOURCES :
{sources_content}

ANALYSE REQUISE :

1. COT REPORT (Commitments of Traders)
   - Positionnement Commercials, Large Speculators, Small Speculators
   - Changements week-over-week
   - Implication Bullish/Bearish

2. DRIVERS MACRO & FONDAMENTAUX
   - Evenements economiques cles (FOMC, CPI, PPI, NFP, tensions geopolitiques, USD)
   - Impact attendu sur l'Or (Bullish/Bearish/Neutral + intensite 1-5)

3. SENTIMENT DE MARCHE
   - Sentiment retail (forums, TradingView, Reddit)
   - Sentiment institutionnel (banques, analystes, rapports)
   - Score global sentiment (-1.0 = extreme bearish, +1.0 = extreme bullish)

4. NIVEAUX TECHNIQUES & ORDER FLOW
   - Supports/resistances majeurs mentionnes
   - High-volume nodes, liquidity pools, order blocks identifies
   - Zones d'absorption, imbalances, manipulations discutees

5. FORECASTS ANALYSTES
   - Objectifs court terme (cette semaine)
   - Objectifs moyen terme (1-3 mois)
   - Consensus bias

TRADING BIAS SUMMARY :
- Direction dominante : BULLISH / BEARISH / NEUTRAL
- Conviction : LOW / MEDIUM / HIGH
- Niveaux cles a surveiller
- Catalyseurs a venir

Reponds en Markdown structure ET inclus a la fin un bloc JSON :
```json
{{
  "bias": "bullish|bearish|neutral",
  "conviction": "low|medium|high",
  "sentiment_score": 0.0,
  "key_support": 0.0,
  "key_resistance": 0.0,
  "short_term_target": 0.0,
  "catalysts": ["catalyst1", "catalyst2"],
  "cot_bias": "bullish|bearish|neutral",
  "macro_bias": "bullish|bearish|neutral"
}}
```"""

# =========================================================
# SCRAPING
# =========================================================

def scrape_sources(urls: list[str], max_chars: int = 3000) -> str:
    """Scrape plusieurs URLs et retourne le contenu concatene."""
    app     = Firecrawl(api_key=FIRECRAWL_KEY)
    content = []

    for url in urls:
        try:
            result = app.scrape(url, formats=["markdown"])
            md = result.markdown if hasattr(result, "markdown") else str(result)
            if md:
                content.append(f"### Source: {url}\n\n{md[:max_chars]}\n\n---\n")
        except Exception as e:
            content.append(f"### Source: {url}\n\nErreur: {e}\n\n---\n")

    return "\n".join(content)


async def scrape_with_search(query: str, limit: int = 5) -> str:
    """Utilise Firecrawl search pour trouver les meilleures sources."""
    try:
        app    = Firecrawl(api_key=FIRECRAWL_KEY)
        result = app.search(query, limit=limit)

        content = []
        if hasattr(result, "data"):
            for item in result.data[:limit]:
                url = getattr(item, "url", "")
                md  = getattr(item, "markdown", "") or getattr(item, "content", "")
                if md:
                    content.append(f"### {url}\n\n{md[:2000]}\n\n---\n")
        return "\n".join(content)
    except Exception as e:
        return f"Erreur search: {e}"


# =========================================================
# ANALYSE GEMINI
# =========================================================

async def analyze_with_gemini(sources_content: str) -> dict:
    """Envoie les donnees scraped a Gemini pour analyse structuree."""
    prompt = GOLD_ANALYSIS_PROMPT.format(sources_content=sources_content[:15000])

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":     0.2,
            "maxOutputTokens": 3000,
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            GEMINI_URL, json=payload,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise HTTPException(resp.status, f"Gemini error: {text[:200]}")
            data = await resp.json()

    raw = data["candidates"][0]["content"]["parts"][0]["text"]

    # Extrait le JSON du markdown
    import re
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
    bias_data  = {}
    if json_match:
        try:
            bias_data = json.loads(json_match.group(1))
        except Exception:
            pass

    return {
        "markdown":  raw,
        "bias_data": bias_data,
    }


# =========================================================
# ENDPOINTS
# =========================================================

@router.get("/gold")
async def get_gold_analysis():
    """
    Analyse complete XAUUSD :
    COT + Macro + Sentiment + Niveaux + Forecasts
    Resultat cache 1h pour economiser les credits Firecrawl.
    """
    # Check cache (1h)
    cache_file = NEWS_DIR / "gold_analysis_latest.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        age  = time.time() - data.get("ts", 0)
        if age < 3600:  # Cache 1 heure
            data["cached"] = True
            data["cache_age_min"] = round(age / 60, 1)
            return data

    # Scrape les sources
    sources_content = ""

    # 1. Search Firecrawl pour les news recentes
    try:
        app = Firecrawl(api_key=FIRECRAWL_KEY)
        search_result = app.search(
            "Gold XAUUSD price analysis order flow COT report today",
            limit=5,
        )
        if hasattr(search_result, "data"):
            for item in search_result.data[:5]:
                url = getattr(item, "url", "")
                md  = getattr(item, "markdown", "") or getattr(item, "content", "")
                if md:
                    sources_content += f"### {url}\n{md[:2000]}\n\n---\n"
    except Exception as e:
        sources_content += f"Search error: {e}\n\n"

    # 2. Scrape Kitco directement
    try:
        app    = Firecrawl(api_key=FIRECRAWL_KEY)
        result = app.scrape("https://www.kitco.com/gold-price-today-usa/", formats=["markdown"])
        md     = result.markdown if hasattr(result, "markdown") else ""
        if md:
            sources_content += f"### Kitco Gold\n{md[:3000]}\n\n---\n"
    except Exception as e:
        sources_content += f"Kitco error: {e}\n\n"

    if not sources_content:
        return {"error": "Impossible de scraper les sources", "ts": time.time()}

    # Analyse Gemini
    analysis = await analyze_with_gemini(sources_content)

    result = {
        "ts":           time.time(),
        "instrument":   "XAUUSD",
        "markdown":     analysis["markdown"],
        "bias":         analysis["bias_data"],
        "sources_used": len(sources_content.split("---")),
        "cached":       False,
    }

    # Sauvegarde cache
    cache_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


@router.get("/gold/bias")
async def get_gold_bias():
    """
    Retourne uniquement le biais tradeable JSON (rapide, pour les agents).
    """
    cache_file = NEWS_DIR / "gold_analysis_latest.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        age  = time.time() - data.get("ts", 0)
        if age < 3600:
            return {
                "bias":      data.get("bias", {}),
                "age_min":   round(age / 60, 1),
                "cached":    True,
                "instrument": "XAUUSD",
            }
    # Force refresh
    result = await get_gold_analysis()
    return {
        "bias":       result.get("bias", {}),
        "age_min":    0,
        "cached":     False,
        "instrument": "XAUUSD",
    }


@router.post("/gold/refresh")
async def refresh_gold_analysis():
    """Force un refresh de l'analyse (ignore le cache)."""
    cache_file = NEWS_DIR / "gold_analysis_latest.json"
    if cache_file.exists():
        cache_file.unlink()
    return await get_gold_analysis()


@router.get("/gold/latest")
async def get_latest_cached():
    """Retourne la derniere analyse sans refaire le scraping."""
    cache_file = NEWS_DIR / "gold_analysis_latest.json"
    if not cache_file.exists():
        raise HTTPException(404, "Aucune analyse disponible — appelle /api/news/gold d'abord")
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    data["age_min"] = round((time.time() - data.get("ts", 0)) / 60, 1)
    return data


@router.get("/search")
async def search_news(q: str = "Gold XAUUSD analysis", limit: int = 5):
    """Recherche rapide via Firecrawl search."""
    try:
        app    = Firecrawl(api_key=FIRECRAWL_KEY)
        result = app.search(q, limit=limit)
        items  = []
        if hasattr(result, "data"):
            for item in result.data:
                items.append({
                    "url":     getattr(item, "url", ""),
                    "title":   getattr(item, "title", ""),
                    "content": (getattr(item, "markdown", "") or getattr(item, "content", ""))[:300],
                })
        return {"results": items, "query": q, "count": len(items)}
    except Exception as e:
        raise HTTPException(500, str(e))
