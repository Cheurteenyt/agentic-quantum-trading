"""
Firecrawl Web-Agent Engine
===========================
Utilise l'API Firecrawl Cloud /v2/agent avec ta clé API.

L'agent exécute des boucles autonomes:
- Planifie (break down goal en steps)
- Agit (browse, scrape, search)
- Observe (parse results)
- Répète jusqu'à complétion

Pas besoin de self-hosted — Firecrawl gère les navigateurs headless.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any
import aiohttp

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

import os
# Configuration API Firecrawl
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
if not FIRECRAWL_API_KEY:
    print("[WARN] FIRECRAWL_API_KEY not set in web_agent.py")
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2"

DATA_DIR = Path("data")
INVESTIGATIONS_DIR = DATA_DIR / "investigations"
INVESTIGATIONS_DIR.mkdir(parents=True, exist_ok=True)


class FirecrawlWebAgent:
    """
    Client pour Firecrawl Web-Agent API (/v2/agent).
    
    Utilise les models Spark 1 optimisés pour agent workflows.
    """
    
    def __init__(self, api_key: str = FIRECRAWL_API_KEY):
        self.api_key = api_key
        self.api_url = FIRECRAWL_API_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Rate limiting
        self._last_request = 0
        self._min_interval = 2.0
        
        # State
        self.active_investigations = {}
        
    async def run(
        self, 
        goal: str, 
        url: str = None,
        timeout: int = 120,
        schema: dict = None,
        stream: bool = False
    ) -> dict:
        """
        Lance une investigation web autonome.

        Args:
            goal: Description naturelle de ce qu'on cherche
            url: URL cible (optionnel)
            timeout: Timeout en secondes
            schema: JSON Schema pour extraction structuree (optionnel)
            stream: Parametre conserve pour compatibilite, non supporte par /v2/agent

        Returns:
            Investigation complete avec:
            {
                "id": "inv_xxx",
                "status": "completed",
                "output": "Resultat final structure",
                "steps_executed": [...],
                "tokens_used": 1234,
                "duration_ms": 45000
            }
        """
        investigation_id = f"inv_{int(time.time())}_{len(self.active_investigations)}"

        payload = {
            "prompt": goal,
        }

        if url:
            payload["urls"] = [url]

        if schema:
            payload["schema"] = schema

        # Firecrawl Agent v2 ne supporte pas le streaming via cette API HTTP.
        # On garde le parametre pour compatibilite d'appel, sans l'envoyer.
        _ = stream

        # Rate limiting
        elapsed = time.time() - self._last_request
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)

        self._last_request = time.time()

        # Sauvegarde state initial
        self.active_investigations[investigation_id] = {
            "id": investigation_id,
            "goal": goal,
            "url": url,
            "status": "running",
            "started_at": time.time(),
            "steps": [],
        }

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout + 30)
            ) as session:
                async with session.post(
                    f"{self.api_url}/agent",
                    headers=self.headers,
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()

                        if result.get("status") == "completed":
                            completion = result
                            firecrawl_job_id = result.get("id")
                        else:
                            firecrawl_job_id = result.get("id")
                            if not firecrawl_job_id:
                                raise Exception(f"Missing Firecrawl job id: {result}")
                            completion = await self._poll_agent_result(
                                firecrawl_job_id,
                                timeout
                            )

                        output = completion.get("data", completion)

                        # Finalise investigation
                        self.active_investigations[investigation_id].update({
                            "status": completion.get("status", "completed"),
                            "output": output,
                            "completed_at": time.time(),
                            "tokens_used": completion.get("creditsUsed", 0),
                            "credits_used": completion.get("creditsUsed", 0),
                            "steps_executed": completion.get("steps", []),
                            "firecrawl_job_id": firecrawl_job_id,
                        })

                        # Sauvegarde persistante
                        await self._save_investigation(
                            investigation_id,
                            self.active_investigations[investigation_id]
                        )

                        return self.active_investigations[investigation_id]

                    error_text = await resp.text()
                    logger.error(f"Firecrawl agent error: {resp.status} - {error_text}")

                    self.active_investigations[investigation_id]["status"] = "failed"
                    self.active_investigations[investigation_id]["error"] = {
                        "status": resp.status,
                        "message": error_text
                    }

                    return {
                        "id": investigation_id,
                        "status": "failed",
                        "error": error_text,
                    }

        except asyncio.TimeoutError:
            logger.error(f"Investigation {investigation_id} timed out")
            self.active_investigations[investigation_id]["status"] = "timeout"
            return {
                "id": investigation_id,
                "status": "timeout",
                "error": "Investigation timed out after {}s".format(timeout),
            }
        except Exception as e:
            logger.error(f"Investigation {investigation_id} failed: {e}")
            self.active_investigations[investigation_id]["status"] = "failed"
            self.active_investigations[investigation_id]["error"] = str(e)
            return {
                "id": investigation_id,
                "status": "failed",
                "error": str(e),
            }
    async def _poll_agent_result(self, task_id: str, max_timeout: int) -> dict:
        """Poll l'API pour récupérer le résultat d'une investigation async."""
        poll_interval = 5
        elapsed = 0
        
        while elapsed < max_timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.api_url}/agent/{task_id}",
                        headers=self.headers
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            
                            if result.get("status") == "completed":
                                return result
                            elif result.get("status") in ["failed", "error"]:
                                raise Exception(f"Agent failed: {result.get('error')}")
                            else:
                                # Still processing
                                await asyncio.sleep(poll_interval)
                                elapsed += poll_interval
                        else:
                            raise Exception(f"Poll error: {resp.status}")
            except Exception as e:
                logger.warning(f"Poll attempt failed: {e}, retrying...")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                
        raise TimeoutError("Task did not complete within timeout")
    
    async def _save_investigation(self, inv_id: str, data: dict):
        """Sauvegarde investigation dans data/investigations/"""
        path = INVESTIGATIONS_DIR / f"{inv_id}.json"
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save investigation {inv_id}: {e}")
    
    def get_investigation_status(self, inv_id: str) -> dict | None:
        """Récupère statut d'une investigation par ID."""
        return self.active_investigations.get(inv_id)
    
    def list_active_investigations(self, limit: int = 20) -> list[dict]:
        """Liste toutes les investigations récentes."""
        all_invs = list(self.active_investigations.values())
        return sorted(all_invs, key=lambda x: x.get("started_at", 0))[-limit:]
    
    def cleanup_old(self, max_age_hours: int = 24):
        """Nettoie investigations plus âgées que max_age_hours."""
        cutoff = time.time() - (max_age_hours * 3600)
        old_ids = [
            inv_id for inv_id, data in self.active_investigations.items()
            if data.get("completed_at", 0) < cutoff or data.get("started_at", 0) < cutoff
        ]
        for inv_id in old_ids:
            del self.active_investigations[inv_id]


# =============================================================================
# AGENTS SPÉCIALISÉS — Wrappers métier autour du moteur Firecrawl
# =============================================================================

class BinanceHunter:
    """
    Agent spécialisé dans la chasse aux nouveaux listings Binance.
    
    Scénario : Whale détecte transfert → lance hunter pour vérifier listing
    """
    
    def __init__(self, web_agent: FirecrawlWebAgent):
        self.agent = web_agent
        self.binance_announcements_url = "https://www.binance.com/en/support/announcement"
        
    async def hunt_new_listings(self, hours_back: int = 1) -> list[dict]:
        """
        Recherche active de nouveaux listings récents.
        
        Utilisation: Le web-agent va naviguer sur la page, chercher les annonces
        récentes, extraire les details structurés.
        """
        
        goal = f"""
        Go to Binance cryptocurrency announcements and find NEW listings in the last {hours_back} hour(s).
        
        Instructions:
        1. Navigate to the new crypto listings announcement page
        2. Filter/search for announcements posted within the last {hours_back} hour(s)
        3. For each listing found, extract:
           - Token symbol (e.g., PEPE, ARB, OP)
           - Full token name
           - Trading pairs available (e.g., USDT, BTC, ETH, FDUSD)
           - When trading starts (UTC timestamp)
           - Deposit opening status
           - Direct link to announcement
        
        4. Return structured JSON array with findings
        
        If no new listings found, return empty array [].
        """
        
        result = await self.agent.run(
            goal=goal,
            url=self.binance_announcements_url,
            timeout=90,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "name": {"type": "string"},
                        "pairs": {"type": "array", "items": {"type": "string"}},
                        "trading_start_utc": {"type": "string"},
                        "deposit_open": {"type": "boolean"},
                        "announcement_url": {"type": "string"},
                        "time_since_posting": {"type": "string"}
                    },
                    "required": ["symbol", "pairs", "trading_start_utc"]
                }
            }
        )
        
        if result.get("status") == "completed":
            output = result.get("output", {})
            if isinstance(output, dict) and "result" in output:
                return output["result"]
            elif isinstance(output, list):
                return output
        return []
    
    async def investigate_token_listing(self, token_symbol: str) -> dict:
        """
        Investigation complète d'un token newly listed.
        
        Checks cross-site: insider transfers, social sentiment, audits.
        """
        goal = f"""
        Conduct deep due diligence investigation on the token {token_symbol} that was just listed on Binance.
        
        Research multiple sources and cross-validate findings:
        
        1. **Insider Activity Check:**
           - Search Etherscan/BSCScan for large transfers of {token_symbol} to Binance in the 24h before listing announcement
           - Check if any known whale addresses accumulated tokens early
           - Look for patterns suggesting insider knowledge
        
        2. **Social Sentiment Analysis:**
           - Check Twitter/X posts about {token_symbol} from top crypto influencers
           - Analyze Discord/Telegram community quality (real users vs bots?)
           - Look for coordinated pump attempts
        
        3. **Contract Security:**
           - Has {token_symbol} been audited by CertiK/Hacken/other reputable firms?
           - Any known vulnerabilities or red flags?
           - Is the contract verified on block explorer?
        
        4. **Team Background:**
           - Anonymous or doxxed team?
           - Track record of previous projects (success/failure)?
           - Social media presence authentic?
        
        5. **Tokenomics Analysis:**
           - Fair distribution or concentrated holdings?
           - Lock-up periods for team/advisor tokens?
           - Vesting schedule transparency?
        
        Return your findings as a detailed JSON report with:
        - Overall risk score (0-100, lower is safer)
        - Confidence level (0-1)
        - Key red flags (if any)
        - Bullish indicators (if any)
        - Recommendation: AVOID/WATCH/CONSIDER/BUY
        """
        
        return await self.agent.run(goal, timeout=180)


class ChainDetective:
    """
    Agent enquêteur sur-chain autonome.
    
    Traque whale movements, token deployments, smart contract analysis.
    """
    
    def __init__(self, web_agent: FirecrawlWebAgent):
        self.agent = web_agent
        
    async def investigate_whale_movement(
        self, 
        wallet_address: str,
        amount_usd: float,
        direction: str,
        token_symbol: str = None
    ) -> dict:
        """
        Investigation complète d'un mouvement whale suspect.
        
        Workflow:
        1. Look up wallet on Etherscan/debank/zapper
        2. Analyze transaction history (patterns, frequency, counterparties)
        3. Check if wallet belongs to known entity (Vitalik, exchange, fund)
        4. Correlate with recent news/events (listings, unlocks, partnerships)
        5. Historical pattern analysis (does this whale dump after transfers?)
        """
        
        goal = f"""
        Investigate this suspicious whale movement:
        
        - Wallet Address: {wallet_address}
        - Amount: ${amount_usd:,.0f} USD
        - Direction: {direction}
        - Token: {token_symbol or "Unknown"}
        
        Research Steps:
        1. **Wallet Profiling:**
           - Use DeBank/Zapper/Etherscan to analyze wallet history
           - What type of holder is this? (retail whale, institutional, exchange cold wallet?)
           - Total portfolio value across chains
           - Average transaction size
        
        2. **Transaction Pattern Analysis:**
           - How often does this whale move funds to/from exchanges?
           - What's their historical sell behavior after deposits?
           - Do they have connections to known insiders/funds?
        
        3. **Entity Identification:**
           - Is this address tagged anywhere (Etherscan labels, Whale Alert)?
           - Associated with any VC firm, market maker, or celebrity?
           - Any public social media presence linked to this wallet?
        
        4. **Event Correlation:**
           - Are there any upcoming catalysts for this token? (unlock, listing, earnings)
           - Did this whale buy during a dip or accumulate over time?
           - Timing suggests opportunistic vs planned exit?
        
        5. **Market Impact Prediction:**
           - Based on amount and historical behavior, likelihood of dump?
           - Estimated selling pressure if liquidated immediately
           - Support/resistance levels based on avg buy price
        
        Return structured intelligence with actionable insights, not just raw data.
        """
        
        explorer_url = f"https://etherscan.io/address/{wallet_address}"
        
        return await self.agent.run(
            goal=goal,
            url=explorer_url,
            timeout=180,
            schema={
                "type": "object",
                "properties": {
                    "wallet_type": {"type": "string"},
                    "portfolio_value_usd": {"type": "number"},
                    "historical_dump_rate": {"type": "number", "description": "0-1 probability"},
                    "confidence_score": {"type": "number", "description": "0-1 confidence"},
                    "dump_probability": {"type": "number", "description": "Probability of sell within 24h"},
                    "key_findings": {"type": "array", "items": {"type": "string"}},
                    "recommendation": {"type": "string"}
                }
            }
        )
    
    async def investigate_new_token(self, token_address: str, chain: str = "ethereum") -> dict:
        """Due diligence complète d'un nouveau token détecté on-chain."""
        
        goal = f"""
        Perform comprehensive due diligence on new token deployed at: {token_address} ({chain})
        
        This is an automatic investigation triggered by token deployment detection.
        
        Investigation Checklist:
        
        1. **Contract Security Assessment:**
           - Verify contract source code on block explorer
           - Check audit reports (CertiK, Hacken, Quantstamp, etc.)
           - Scan for common vulnerabilities (honeypot, mint function, proxy risks)
           - Review ownership structure (renounced? multi-sig?)
        
        2. **Team Verification:**
           - Team identity anonymous or doxxed?
           - LinkedIn/Twitter verification attempts
           - Previous project track record
           - Community trust signals (AMAs, GitHub activity)
        
        3. **Tokenomics Deep Dive:**
           - Initial distribution fairness (team % vs public %)
           - Liquidity lock duration and verification
           - Vesting schedules for insiders
           - Inflation/deflation mechanisms
        
        4. **Community & Marketing:**
           - Twitter/Discord/Telegram engagement quality
           - Bot detection in social channels
           - Influencer relationships (paid vs organic?)
           - Roadmap credibility
        
        5. **Competitive Analysis:**
           - How does this token compare to similar projects?
           - Unique value proposition or copycat?
           - Market positioning and target audience
        
        6. **Red Flag Detection:**
           - Honeypot mechanics
           - Unlimited minting capability
           - Team can drain liquidity
           - Suspicious transaction patterns
        
        Output: Structured risk assessment with numerical scores.
        """
        
        explorer_map = {
            "ethereum": f"https://etherscan.io/token/{token_address}",
            "bsc": f"https://bscscan.com/token/{token_address}",
            "polygon": f"https://polygonscan.com/token/{token_address}",
            "arbitrum": f"https://arbiscan.io/token/{token_address}",
        }
        
        explorer_url = explorer_map.get(chain.lower(), explorer_map["ethereum"])
        
        return await self.agent.run(goal, url=explorer_url, timeout=180)


class SentimentScanner:
    """
    Agent analyseur de sentiment marché multi-sources.
    
    Sources combinées: News crypto, social media, on-chain narratives.
    """
    
    def __init__(self, web_agent: FirecrawlWebAgent):
        self.agent = web_agent
        
    async def scan_sentiment(self, symbols: list[str]) -> dict:
        """
        Scan global sentiment pour plusieurs tokens simultanément.
        
        Utilisation: Funding rate spike detected → check sentiment
        """
        
        goal = f"""
        Analyze current market sentiment for these cryptocurrencies: {', '.join(symbols)}
        
        Research multiple sources and synthesize findings:
        
        **Sources to Monitor:**
        
        1. **News Aggregators:**
           - CryptoPanic dashboard (latest articles, sentiment tags)
           - Coindesk/Cointelegraph headlines
           - Sector-specific news (DeFi, NFTs, Layer 2, etc.)
        
        2. **Social Media Signals:**
           - Twitter/X trending mentions (volume spike detection)
           - Top crypto influencer sentiment (bullish/bearish posts)
           - Reddit r/CryptoCurrency and r/Bitcoin thread sentiment
           - Discord community activity levels
        
        3. **On-Chain Narratives:**
           - Glassnode/Santiment insights (whale accumulation/distribution)
           - Exchange flow trends (inflows = bearish, outflows = bullish)
           - Stablecoin supply ratio changes
        
        **Output Structure per Symbol:**
        ```json
        {{
          "symbol": "BTC",
          "overall_sentiment": "bullish|bearish|neutral",
          "sentiment_score": 0.72,  // Range: -1 (extreme bearish) to +1 (extreme bullish)
          "confidence": 0.85,  // How reliable is this reading?
          "volume_change_24h": "+23%",  // Social mention volume change
          "key_drivers": [
            "ETF inflow surge detected",
            "Whale accumulation trend increasing",
            "Positive regulatory news from SEC"
          ],
          "contrarian_signals": [
            "Retail FOMO indicator elevated (warning sign)"
          ],
          "timeframe_outlook": {
            "short_term_24h": "bullish",
            "medium_term_7d": "neutral",
            "long_term_30d": "bullish"
          }
        }}
        ```
        
        Return JSON array with one object per symbol.
        """
        
        url = "https://cryptopanic.com/dashboard/"
        
        result = await self.agent.run(
            goal=goal,
            url=url,
            timeout=120,
            schema={
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "overall_sentiment": {"type": "string"},
                        "sentiment_score": {"type": "number"},
                        "confidence": {"type": "number"},
                        "key_drivers": {"type": "array", "items": {"type": "string"}}
                    }
                }
            }
        )
        
        if result.get("status") == "completed":
            output = result.get("output", {})
            if isinstance(output, dict) and "result" in output:
                return output["result"]
            return output
        return {}
    
    async def investigate_funding_spike(
        self, 
        symbol: str, 
        funding_rate: float,
        exchange: str = "binance"
    ) -> dict:
        """
        Pourquoi le funding rate a-t-il spiqué? Investigation causale.
        """
        
        goal = f"""
        Investigate why the funding rate for {symbol} on {exchange} just spiked to {funding_rate:.4f}% (unusually high).
        
        This requires multi-source correlation:
        
        1. **Catalyst Search:**
           - Any major news about {symbol}? (partnerships, upgrades, hacks)
           - Upcoming events? (token unlock, ETF decision, earnings)
           - Regulatory developments affecting this specific asset?
        
        2. **Position Data:**
           - Current long/short ratio on major exchanges
           - Open Interest trend (rising = leverage building, dangerous)
           - Liquidation heatmaps (where are cascades likely?)
        
        3. **Whale Activity:**
           - Large positions opened recently? (check whale alert feeds)
           - Accumulation or distribution pattern?
           - Institutional vs retail positioning divergence?
        
        4. **Market Maker Analysis:**
           - Unusual options activity? (put/call ratio skew)
           - Basis trade opportunities exploited?
           - Arbitrage flows between spot/futures?
        
        5. **Historical Precedent:**
           - Similar funding spikes in past → what happened next?
           - Average duration of such conditions
           - Typical resolution (price crash, slow bleed, squeeze?)
        
        Synthesis Required:
        - Is this ORGANIC demand (legitimate bullish conviction)?
        - OR MANIPULATION SETUP (coordinated squeeze preparation)?
        - Likelihood of long squeeze vs short squeeze?
        - Recommended action: Avoid, Wait, or Trade contrarian?
        
        Return structured risk/reward assessment.
        """
        
        return await self.agent.run(goal, timeout=120)


# =============================================================================
# FACTORY & STATE ACCESS
# =============================================================================

_web_agent_instance: FirecrawlWebAgent = None


def init_web_agent(api_key: str = FIRECRAWL_API_KEY) -> FirecrawlWebAgent:
    """Initialise l'instance globale du web-agent."""
    global _web_agent_instance
    _web_agent_instance = FirecrawlWebAgent(api_key)
    # pas de fragment de clé dans les journaux (ronde 8)
    print("[WEB-AGENT] Initialized with Firecrawl API (key: set)")
    return _web_agent_instance


def get_web_agent() -> FirecrawlWebAgent:
    """Récupère l'instance globale du web-agent."""
    if _web_agent_instance is None:
        raise RuntimeError("Web agent not initialized. Call init_web_agent() first.")
    return _web_agent_instance


def get_specialized_agents() -> dict:
    """
    Factory pour obtenir tous les agents spécialisés.
    
    Usage:
        agents = get_specialized_agents()
        listings = await agents['binance_hunter'].hunt_new_listings()
    """
    agent = get_web_agent()
    return {
        "binance_hunter": BinanceHunter(agent),
        "chain_detective": ChainDetective(agent),
        "sentiment_scanner": SentimentScanner(agent),
    }
