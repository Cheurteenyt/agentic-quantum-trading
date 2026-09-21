"""Alpha Lab token-risk and sellability data models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RiskFlag(BaseModel):
    code: str
    severity: str
    points: int
    detail: str


class SellabilityProbe(BaseModel):
    token_address: str | None = None
    chain: str | None = None
    dexscreener: dict[str, Any] | None = None
    honeypot_api: dict[str, Any] | None = None
    explorer_scrape: dict[str, Any] | None = None
    consensus: str | None = None
    overall_sellable: bool | None = None
    sellability_confidence: float | None = None
    auto_flags: list[RiskFlag] = Field(default_factory=list)


class TokenRiskResult(BaseModel):
    token: str = "unknown"
    chain: str = "unknown"
    risk_score: int = 0
    sellability_score: int = 100
    block_trade: bool = False
    profit_integrity: str = "unknown"
    flags: list[RiskFlag] = Field(default_factory=list)
    sellability_probe: SellabilityProbe | None = None
    source_policy: str = (
        "token_risk_requires_traceable_sources; insufficient sellability, contract, "
        "holder or liquidity proof keeps the verdict research-only/inconclusive"
    )
    source_trace: dict[str, Any] = Field(default_factory=dict)
    missing_proofs: list[str] = Field(default_factory=list)
    required_proofs: list[str] = Field(default_factory=lambda: [
        "successful sell transaction for the watched wallet or a same-route simulation",
        "DEX quote/route proving the configured position size can exit",
        "contract scan for freeze, blacklist, pause, proxy, mint and owner privileges",
        "holder concentration and LP lock/burn evidence",
        "timestamped liquidity snapshot at detection and exit",
    ])
