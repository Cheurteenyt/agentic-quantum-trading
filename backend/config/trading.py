"""
Trading Agent Configuration
Central configuration module for the trading agent system.
"""

from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ExchangeConfig(BaseModel):
    """Configuration for a single exchange."""

    name: str = Field(..., description="Exchange name (binance, bybit, etc.)")
    api_key: Optional[str] = Field(None, description="API key for the exchange")
    api_secret: Optional[str] = Field(None, description="API secret for the exchange")
    enabled: bool = Field(True, description="Whether this exchange is enabled")
    base_url: Optional[str] = Field(None, description="Base API URL")
    sandbox: bool = Field(False, description="Use sandbox/test environment")
    rate_limit: int = Field(10, description="Max requests per minute")


class TradingConfig(BaseSettings):
    """Main trading configuration."""

    # Environment
    environment: str = Field("production", description="Environment (production/test)")

    # Trading parameters
    default_symbol: str = Field("BTC/USDT", description="Default trading pair")
    leverage: float = Field(1.0, description="Default leverage")
    stop_loss_pct: float = Field(2.0, description="Default stop loss percentage")
    take_profit_pct: float = Field(4.0, description="Default take profit percentage")

    # Position sizing
    max_position_size: float = Field(0.1, description="Max position size as % of portfolio")
    position_scale: float = Field(0.25, description="Position scaling factor")

    # Risk management
    max_daily_loss: float = Field(5.0, description="Max daily loss percentage")
    max_concurrent_positions: int = Field(3, description="Max open positions")
    risk_per_trade: float = Field(1.0, description="Risk per trade as % of portfolio")

    # Time parameters
    session_start: str = Field("09:00", description="Trading session start time")
    session_end: str = Field("17:00", description="Trading session end time")
    cooldown_minutes: int = Field(5, description="Cooldown between trades")

    # Exchanges
    exchanges: List[ExchangeConfig] = Field(
        [],
        description="List of configured exchanges",
    )

    # Stockage : SQLite, un FICHIER. Aucun serveur de base dans ce projet
    # (3.3) — `database_url` et `redis_url` ont été retirés : ils
    # déclaraient une architecture jamais utilisée (0 `psycopg2`,
    # 0 `import redis`, 419 `sqlite3.connect`) et aucun code ne les lisait.
    # `model_config` porte `extra = "ignore"` : un .env qui les contient
    # encore ne casse pas, la clé est simplement ignorée.

    # Model provider
    model_provider: str = Field(
        "ollama",
        description="AI model provider (ollama, openrouter, etc.)",
    )

    ollama_base_url: str = Field(
        "http://localhost:11434",
        description="Ollama base URL",
    )

    ollama_model: str = Field(
        "qwen3.5",
        description="Default Ollama model to use",
    )

    # Gateway
    gateway_port: int = Field(8000, description="Gateway server port")
    gateway_enabled: bool = Field(False, description="Enable gateway")

    @property
    def max_open_orders(self) -> int:
        """Calculate max open orders based on positions."""

        return self.max_concurrent_positions * 3

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


def get_config() -> TradingConfig:
    """Get the trading configuration."""

    return TradingConfig()


_config = None


def get_singleton_config() -> TradingConfig:
    """Get singleton config instance."""

    global _config
    if _config is None:
        _config = TradingConfig()
    return _config
