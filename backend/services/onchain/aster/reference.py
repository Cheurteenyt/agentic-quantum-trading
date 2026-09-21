"""Official Aster reference anchors used by read-only research lanes."""

from __future__ import annotations

from typing import Any

from services.onchain_chains import normalize_chain as _normalize_chain


ASTER_DEX_REFERENCE_SOURCE_URL = "https://docs.asterdex.com/overview/what-is-aster/our-smart-contracts"
ASTER_DEX_SPOT_DEPOSIT_SOURCE_URL = "https://docs.asterdex.com/trading/spot/deposit-and-withdrawal-guide"
ASTER_TOKEN_SOURCE_URL = "https://docs.asterdex.com/usdaster/overview"
ASTER_DEX_FUND_FLOW_COLLECTION_CONFIRM = "COLLECT_ASTER_DEX_FUND_FLOW_DATA"
ASTER_DEX_PAGINATED_FUND_FLOW_COLLECTION_CONFIRM = "COLLECT_ASTER_DEX_PAGINATED_FUND_FLOW_DATA"
ASTER_SOURCE_WALLET_TOKEN_FLOW_COLLECTION_CONFIRM = "COLLECT_ASTER_SOURCE_WALLET_TOKEN_FLOW_DATA"

ASTER_DEX_REFERENCE_ADDRESSES = [
    {
        "chain": "bsc",
        "address": "0x128463a60784c4d3f46c23af3f65ed859ba87974",
        "component": "Aster Treasury Contract",
        "reference_role": "treasury_contract",
        "collectable_as_destination": True,
        "source_url": ASTER_DEX_REFERENCE_SOURCE_URL,
        "source_status": "official_docs_exact_chain_address",
    },
    {
        "chain": "eth",
        "address": "0x604dd02d620633ae427888d41bfd15e38483736e",
        "component": "Aster Treasury Contract",
        "reference_role": "treasury_contract",
        "collectable_as_destination": True,
        "source_url": ASTER_DEX_REFERENCE_SOURCE_URL,
        "source_status": "official_docs_exact_chain_address",
    },
    {
        "chain": "scroll",
        "address": "0x7be980e327692cf11e793a0d141d534779af8ef4",
        "component": "Aster Treasury Contract",
        "reference_role": "treasury_contract",
        "collectable_as_destination": True,
        "source_url": ASTER_DEX_REFERENCE_SOURCE_URL,
        "source_status": "official_docs_exact_chain_address",
    },
    {
        "chain": "arbitrum",
        "address": "0x9e36cb86a159d479ced94fa05036f235ac40e1d5",
        "component": "Aster Treasury Contract",
        "reference_role": "treasury_contract",
        "collectable_as_destination": True,
        "source_url": ASTER_DEX_REFERENCE_SOURCE_URL,
        "source_status": "official_docs_exact_chain_address",
    },
    {
        "chain": "bsc",
        "address": "0x000ae314e2a2172a039b26378814c252734f556a",
        "component": "$ASTER Token Contract",
        "reference_role": "token_contract",
        "collectable_as_destination": False,
        "source_url": ASTER_TOKEN_SOURCE_URL,
        "source_status": "official_docs_exact_chain_address",
    },
]


def _aster_dex_reference_addresses(chain: str | None = None) -> list[dict[str, Any]]:
    requested_chain = _normalize_chain(chain or "") if chain else None
    rows: list[dict[str, Any]] = []
    for row in ASTER_DEX_REFERENCE_ADDRESSES:
        row_chain = _normalize_chain(row.get("chain") or "")
        if requested_chain and row_chain != requested_chain:
            continue
        item = dict(row)
        item["chain"] = row_chain
        item["address"] = str(row.get("address") or "").strip().lower()
        rows.append(item)
    return rows

