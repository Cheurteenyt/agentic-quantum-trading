from __future__ import annotations
import json
import os
import shutil
import sqlite3
import time
import urllib.request
from typing import Any

# Config — cles lues depuis l'environnement (backend/.env charge par main.py),
# JAMAIS en dur dans le source (elles etaient ici avant le 2026-09-21, purgees).
_ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY", "")
_COVALENT_KEY = os.getenv("COVALENT_API_KEY", "")
_COVALENT_CHAINID = {"bsc": "56", "eth": "1"}
_ETHERSCAN_CHAINID = {"bsc": 56, "eth": 1}

def _first_env(names: tuple[str, ...], default: str) -> tuple[str, str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value, name
    return default, "public_rpc"


_RPCS = {
    "bsc": _first_env(("HERMES_RPC_BSC", "BSC_RPC", "BSC_RPC_URL"), "https://bsc-dataseed.binance.org/")[0],
    "eth": _first_env(("HERMES_RPC_ETHEREUM", "HERMES_RPC_ETH", "ETH_RPC", "ETH_RPC_URL", "HERMES_ETH_RPC"), "https://rpc.flashbots.net")[0],
}

_RPC_SOURCE = {
    "bsc": _first_env(("HERMES_RPC_BSC", "BSC_RPC", "BSC_RPC_URL"), "https://bsc-dataseed.binance.org/")[1],
    "eth": _first_env(("HERMES_RPC_ETHEREUM", "HERMES_RPC_ETH", "ETH_RPC", "ETH_RPC_URL", "HERMES_ETH_RPC"), "https://rpc.flashbots.net")[1],
}
_RPC_FALLBACKS = {
    "eth": ("https://eth.llamarpc.com", "https://ethereum.publicnode.com"),
    "bsc": ("https://bsc.publicnode.com", "https://bsc-dataseed1.binance.org/"),
}

_MIN_LIQUIDITY_USD = 50_000
_MIN_VOLUME_24H = 10_000
_MIN_TOKEN_VALUE_USD = 1.0
_MIN_TOKEN_AGE_DAYS = 7
_MAX_TOP_HOLDER_PCT = 50.0
_MAX_VOLUME_SPIKE_RATIO = 5.0  # volume h1 > 5x avg -> suspicious
_MAX_TOKEN_PRICE_USD = 1_000_000
_MAX_VALUE_TO_LIQUIDITY_RATIO = 50.0

_STABLE_QUOTES_BY_CHAIN: dict[str, set[str]] = {
    "eth": {"weth", "usdt", "usdc", "dai"},
    "bsc": {"wbnb", "usdt", "usdc", "busd", "dai"},
}

_DEX_CHAIN_ALIASES = {
    "eth": "ethereum",
    "ethereum": "ethereum",
    "bsc": "bsc",
    "bnb": "bsc",
    "binance-smart-chain": "bsc",
    "polygon": "polygon",
    "matic": "polygon",
    "base": "base",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
}

_PRICE_CACHE: dict[str, tuple[float, float]] = {}
_PRICE_CACHE_TTL = 300
_NATIVE_PRICE_CACHE: dict[str, tuple[float, float]] = {}
_NATIVE_PRICE_TTL = 300
_NATIVE_TOKENS = {
    "bsc": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",   # WBNB
    "eth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",   # WETH
}
_RPC_TOKEN_META_CACHE: dict[str, tuple[dict[str, Any], float]] = {}
_RPC_TOKEN_META_TTL = 3600
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_RPC_TRANSFER_LOOKBACK = {"eth": 50_000, "bsc": 120_000}
_RPC_LOG_MAX_RESULTS = 20


def _is_plausible_token_price(price_usd: Any) -> bool:
    try:
        price = float(price_usd or 0)
    except (TypeError, ValueError):
        return False
    return 0 < price <= _MAX_TOKEN_PRICE_USD


def _is_plausible_wallet_value(value_usd: Any, liquidity_usd: Any) -> bool | None:
    """Le plafond de valeur est-il tenable compte tenu de la liquidité ?

    Trois verdicts, et c'est tout l'intérêt (issue #271) :
      True  plausible — la liquidité est connue et la valeur tient dessous
      False non plausible — la valeur dépasse la liquidité (ou est absurde)
      None  INDÉCIDABLE — la liquidité est INCONNUE

    Avant, `float(liquidity_usd or 0)` faisait `None -> 0.0`, et le `return
    True` final était atteint que la liquidité soit 0 parce que le token est
    réellement illiquide OU parce que l'API est tombée. Les deux états étaient
    écrasés en un seul, et l'appelant lisait « plausible ». Un million de
    dollars de valeur sans liquidité connue passait donc le contrôle. Le
    troisième verdict force l'appelant à TRAITER le cas inconnu au lieu de le
    confondre avec le cas sain.
    """
    try:
        value = float(value_usd or 0)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if value >= 1_000_000_000_000:
        return False
    # Liquidité inconnue : on ne peut pas conclure, on ne décide pas à la place
    # de la donnée (fail-closed côté confiance, cf. appelant).
    if liquidity_usd is None:
        return None
    try:
        liquidity = float(liquidity_usd)
    except (TypeError, ValueError):
        return None
    if liquidity < 0:
        return None
    if liquidity > 0 and value > liquidity * _MAX_VALUE_TO_LIQUIDITY_RATIO:
        return False
    return True


def _normalize_dex_chain(chain: Any) -> str:
    value = str(chain or "").lower().strip()
    return _DEX_CHAIN_ALIASES.get(value, value)


def _get_native_price_usd(chain: str) -> float | None:
    """Get native coin price (BNB/ETH) via DexScreener."""
    now = time.time()
    if chain in _NATIVE_PRICE_CACHE:
        p, ts = _NATIVE_PRICE_CACHE[chain]
        if now - ts < _NATIVE_PRICE_TTL:
            return p
    token = _NATIVE_TOKENS.get(chain)
    if not token:
        return None
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        pairs = data.get("pairs") or []
        for p in pairs:
            quote = (p.get("quoteToken", {}).get("symbol") or "").lower()
            base_sym = (p.get("baseToken", {}).get("symbol") or "").lower()
            if base_sym not in ("weth", "wbnb"):
                continue
            if quote not in ("usdt", "usdc", "dai"):
                continue
            price = float(p.get("priceUsd") or 0)
            # Sanity check: ETH should be > 00, BNB > 0
            if chain == "eth" and price < 100:
                continue
            if chain == "bsc" and price < 10:
                continue
                continue
            price = float(p.get("priceUsd") or 0)
            if price > 0:
                _NATIVE_PRICE_CACHE[chain] = (price, now)
                return price
    except Exception:
        pass
    return None

_SERVICE_DIR = os.path.dirname(__file__)
_DATA_DIR = os.path.abspath(os.path.join(_SERVICE_DIR, "..", "data", "wallets"))
os.makedirs(_DATA_DIR, exist_ok=True)
_LEGACY_DB_PATH = os.path.abspath(os.path.join(_SERVICE_DIR, "..", "data", "legacy", "wallet_cache.db"))
_DB_PATH = os.path.join(_DATA_DIR, "wallet_cache.db")
if not os.path.exists(_DB_PATH) and os.path.exists(_LEGACY_DB_PATH):
    shutil.copy2(_LEGACY_DB_PATH, _DB_PATH)
_CACHE_TTL = 300

# # DB 
def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_meta (
            token_address TEXT NOT NULL,
            chain TEXT NOT NULL,
            symbol TEXT,
            decimals INTEGER DEFAULT 18,
            price_usd REAL,
            liquidity_usd REAL,
            volume_24h REAL,
            confidence TEXT,
            pair_validated INTEGER DEFAULT 0,
            top_holder_pct REAL DEFAULT 0,
            age_days REAL,
            last_updated REAL,
            PRIMARY KEY (token_address, chain)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wallet_token_cache (
            wallet TEXT NOT NULL,
            chain TEXT NOT NULL,
            token_address TEXT NOT NULL,
            balance REAL,
            value_usd REAL,
            confidence TEXT,
            last_updated REAL,
            PRIMARY KEY (wallet, chain, token_address)
        )
    """)
    conn.commit()
    conn.close()


_init_db()

# # Helpers 
def _rpc_evm(chain: str, method: str, params: list[Any]) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": int(time.time() * 1000)}).encode()
    req = urllib.request.Request(_RPCS[chain], data=payload, headers={"Content-Type": "application/json", "User-Agent": "Hermes/1.0"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.loads(resp.read().decode()).get("result")


def _rpc_candidates(chain: str) -> list[tuple[str, str]]:
    primary = (_RPCS[chain], _RPC_SOURCE.get(chain, "public_rpc"))
    fallbacks = [(url, "public_rpc_fallback") for url in _RPC_FALLBACKS.get(chain, ()) if url != primary[0]]
    return [primary, *fallbacks]


def _rpc_evm_with_source(chain: str, method: str, params: list[Any]) -> tuple[Any, str]:
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": int(time.time() * 1000)}).encode()
    last_error = "rpc_error"
    for url, source in _rpc_candidates(chain):
        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Hermes/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
            if data.get("error"):
                last_error = str(data["error"].get("message") or "rpc_error")
                continue
            return data.get("result"), source
        except Exception as exc:
            last_error = type(exc).__name__
    raise RuntimeError(last_error)


def _etherscan_proxy_eth_call(chain: str, token_address: str, data: str) -> tuple[Any, str]:
    chainid = _ETHERSCAN_CHAINID.get(chain, 1)
    sep = chr(38)
    url = (
        f"https://api.etherscan.io/v2/api?chainid={chainid}{sep}module=proxy{sep}action=eth_call"
        f"{sep}to={token_address.lower()}{sep}data={data}{sep}tag=latest{sep}apikey={_ETHERSCAN_KEY}"
    )
    payload = _etherscan_call(url)
    if payload and payload.get("result"):
        return payload.get("result"), "etherscan_proxy_eth_call"
    raise RuntimeError(str(payload.get("message") if isinstance(payload, dict) else "proxy_error"))


def _hex_to_uint(hex_str: str) -> int:
    if not hex_str or hex_str == "0x":
        return 0
    return int(hex_str, 16)


def _address_topic(address: str) -> str:
    clean = address.lower().replace("0x", "")
    return "0x" + clean.rjust(64, "0")


def _decode_abi_string(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x") or value == "0x":
        return None
    data = value[2:]
    try:
        if len(data) >= 128:
            offset = int(data[:64], 16)
            length_pos = offset * 2
            length = int(data[length_pos:length_pos + 64], 16)
            start = length_pos + 64
            raw = bytes.fromhex(data[start:start + length * 2])
            decoded = raw.decode("utf-8", errors="ignore").strip("\x00").strip()
            if decoded:
                return decoded
        if len(data) >= 64:
            raw = bytes.fromhex(data[:64])
            decoded = raw.rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
            if decoded and decoded.isprintable():
                return decoded
    except Exception:
        return None
    return None


def _source_item(kind: str, source: str, chain: str, ok: bool, detail: str | None = None) -> dict[str, Any]:
    item = {"kind": kind, "source": source, "chain": chain, "ok": bool(ok)}
    if detail:
        item["detail"] = detail
    return item


def _rpc_contract_proof(chain: str, token_address: str) -> dict[str, Any]:
    """Verify that a token contract exists on the requested chain via RPC."""
    proof = {
        "exists": False,
        "chain": chain,
        "rpc_source": _RPC_SOURCE.get(chain, "unknown_rpc"),
        "bytecode_size": 0,
    }
    try:
        code, source = _rpc_evm_with_source(chain, "eth_getCode", [token_address.lower(), "latest"])
        proof["rpc_source"] = source
        if isinstance(code, str) and code not in ("", "0x"):
            proof["exists"] = True
            proof["bytecode_size"] = max(0, (len(code) - 2) // 2)
    except Exception as exc:
        proof["error"] = type(exc).__name__
    return proof


def _rpc_erc20_metadata(chain: str, token_address: str) -> dict[str, Any]:
    """Read ERC-20 metadata directly from the contract via eth_call."""
    cache_key = f"{chain}:{token_address.lower()}"
    now = time.time()
    cached = _RPC_TOKEN_META_CACHE.get(cache_key)
    if cached and now - cached[1] < _RPC_TOKEN_META_TTL:
        return cached[0]

    meta: dict[str, Any] = {
        "chain": chain,
        "source": _RPC_SOURCE.get(chain, "unknown_rpc"),
        "symbol": None,
        "decimals": None,
        "total_supply_raw": None,
        "total_supply": None,
        "ok": False,
        "errors": [],
    }

    calls = {
        "symbol": "0x95d89b41",
        "decimals": "0x313ce567",
        "total_supply": "0x18160ddd",
    }
    sources: list[str] = []
    try:
        try:
            symbol_raw, source = _rpc_evm_with_source(chain, "eth_call", [{"to": token_address.lower(), "data": calls["symbol"]}, "latest"])
        except Exception:
            symbol_raw, source = _etherscan_proxy_eth_call(chain, token_address, calls["symbol"])
        sources.append(source)
        meta["symbol"] = _decode_abi_string(symbol_raw)
    except Exception as exc:
        meta["errors"].append(f"symbol:{type(exc).__name__}")

    try:
        try:
            decimals_raw, source = _rpc_evm_with_source(chain, "eth_call", [{"to": token_address.lower(), "data": calls["decimals"]}, "latest"])
        except Exception:
            decimals_raw, source = _etherscan_proxy_eth_call(chain, token_address, calls["decimals"])
        sources.append(source)
        if isinstance(decimals_raw, str) and decimals_raw not in ("", "0x"):
            decimals = _hex_to_uint(decimals_raw)
            if 0 <= decimals <= 36:
                meta["decimals"] = decimals
    except Exception as exc:
        meta["errors"].append(f"decimals:{type(exc).__name__}")

    try:
        try:
            supply_raw, source = _rpc_evm_with_source(chain, "eth_call", [{"to": token_address.lower(), "data": calls["total_supply"]}, "latest"])
        except Exception:
            supply_raw, source = _etherscan_proxy_eth_call(chain, token_address, calls["total_supply"])
        sources.append(source)
        if isinstance(supply_raw, str) and supply_raw not in ("", "0x"):
            total_supply_raw = _hex_to_uint(supply_raw)
            meta["total_supply_raw"] = total_supply_raw
            if isinstance(meta.get("decimals"), int):
                meta["total_supply"] = total_supply_raw / (10 ** int(meta["decimals"]))
    except Exception as exc:
        meta["errors"].append(f"totalSupply:{type(exc).__name__}")

    meta["ok"] = bool(meta.get("symbol") or meta.get("decimals") is not None or meta.get("total_supply_raw") is not None)
    if sources:
        meta["source"] = "+".join(dict.fromkeys(sources))
    _RPC_TOKEN_META_CACHE[cache_key] = (meta, now)
    return meta


# # Etherscan V2 
def _etherscan_url(chain: str, action: str, **params: str) -> str:
    chainid = _ETHERSCAN_CHAINID.get(chain, 1)
    sep = chr(38)
    base = f"https://api.etherscan.io/v2/api?chainid={chainid}{sep}module=account{sep}action={action}"
    for k, v in params.items():
        base += f"{sep}{k}={v}"
    base += f"{sep}apikey={_ETHERSCAN_KEY}"
    return base


def _etherscan_call(url: str) -> Any:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _etherscan_tokentx(chain: str, address: str) -> list[dict]:
    url = _etherscan_url(chain, "tokentx", address=address.lower())
    data = _etherscan_call(url)
    if data and data.get("status") == "1" and isinstance(data.get("result"), list):
        return data["result"]
    return []


def _etherscan_tokenbalance(chain: str, contract: str, address: str) -> str | None:
    url = _etherscan_url(chain, "tokenbalance", contractaddress=contract.lower(), address=address.lower())
    data = _etherscan_call(url)
    if data and data.get("status") == "1":
        return str(data.get("result", "0"))
    return None


# # DexScreener 
_DEX_CACHE: dict[str, tuple[dict, float]] = {}
_DEX_CACHE_TTL = 120


def _get_dexscreener_data(token_address: str, chain: str = "eth") -> dict[str, Any]:
    """Fetch token data from DexScreener with pair validation and quality scoring.
    Returns {price_usd, liquidity_usd, volume_24h, market_cap, confidence, pair_validated, top_holder_pct}."""
    requested_chain = _normalize_dex_chain(chain)
    cache_key = f"{requested_chain}:{token_address.lower()}"
    now = time.time()
    if cache_key in _DEX_CACHE:
        cached, ts = _DEX_CACHE[cache_key]
        if now - ts < _DEX_CACHE_TTL:
            return cached

    # Use the chain-scoped endpoint first. The generic token endpoint can return
    # Ethereum liquidity for a BSC balance when contracts/symbols collide.
    url = f"https://api.dexscreener.com/tokens/v1/{requested_chain}/{token_address}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        # Issue #271 : « API muette » n'est PAS « pas de pair ». Avant, on
        # renvoyait {} — indistinguable d'une réponse vide, donc `liquidity_usd`
        # disparaissait (le `.get()` de l'appelant rendait None) et le contrôle
        # de plausibilité lisait None comme 0 donc « plausible ». On renvoie
        # désormais un bloc explicite : liquidité None (inconnue, pas nulle),
        # marqueur `api_error`, confiance low. L'appelant distingue enfin les
        # deux causes.
        result = {
            "dex_chain": requested_chain,
            "api_error": True,
            "price_usd": None,
            "liquidity_usd": None,
            "volume_24h": 0,
            "market_cap": 0,
            "confidence": "low",
            "pair_validated": False,
            "top_holder_pct": 0,
            "checks": ["api_error"],
        }
        _DEX_CACHE[cache_key] = (result, now)
        return result

    pairs = data if isinstance(data, list) else (data.get("pairs") or [])
    if not pairs:
        result = {
            "dex_chain": requested_chain,
            "chain_mismatch": True,
            "price_usd": None,
            "liquidity_usd": 0,
            "volume_24h": 0,
            "market_cap": 0,
            "confidence": "low",
            "pair_validated": False,
            "top_holder_pct": 0,
            "checks": ["no_chain_pair"],
        }
        _DEX_CACHE[cache_key] = (result, now)
        return result

    chain_pairs = [p for p in pairs if _normalize_dex_chain(p.get("chainId")) == requested_chain]
    chain_mismatch = False
    if chain_pairs:
        pairs = chain_pairs
    else:
        # Critical: do not price a wallet balance with liquidity from another
        # chain. Example: BSC wallet balance + Ethereum ASTEROID market.
        result = {
            "dex_chain": requested_chain,
            "chain_mismatch": True,
            "price_usd": None,
            "liquidity_usd": 0,
            "volume_24h": 0,
            "market_cap": 0,
            "confidence": "low",
            "pair_validated": False,
            "top_holder_pct": 0,
            "checks": ["chain_mismatch"],
        }
        _DEX_CACHE[cache_key] = (result, now)
        return result

    # Chain-aware quote validation
    stable_quotes = _STABLE_QUOTES_BY_CHAIN.get(chain, _STABLE_QUOTES_BY_CHAIN["eth"])
    validated_pairs = []
    indirect_pairs = []
    for p in pairs:
        base = (p.get("baseToken", {}).get("symbol") or "").lower()
        quote = (p.get("quoteToken", {}).get("symbol") or "").lower()
        if quote in stable_quotes or base in stable_quotes:
            validated_pairs.append(p)
        elif quote in ("weth", "wbnb") or base in ("weth", "wbnb"):
            indirect_pairs.append(p)

    pair_validated = len(validated_pairs) > 0
    pair_indirect = len(indirect_pairs) > 0 and not pair_validated
    if pair_validated:
        pairs_to_use = validated_pairs
    elif pair_indirect:
        pairs_to_use = indirect_pairs
    else:
        pairs_to_use = pairs[:3]

    total_liq = 0.0
    total_vol = 0.0
    best_price = 0.0
    best_price_liq = 0.0
    weighted_price = 0.0
    weighted_liq = 0.0
    best_mcap = 0.0
    top_holder_pct = 0.0
    best_pair_chain = ""

    for p in pairs_to_use:
        liq = p.get("liquidity", {}).get("usd") or 0
        vol = p.get("volume", {}).get("h24") or 0
        price = float(p.get("priceUsd") or 0)
        mcap = float(p.get("marketCap") or 0)
        # Get holders info if available
        holders = p.get("holders")
        if holders and isinstance(holders, list) and len(holders) > 0:
            top_pct = holders[0].get("percent") or 0
            if top_pct > top_holder_pct:
                top_holder_pct = top_pct

        if liq and liq > 0:
            total_liq += liq
            if _is_plausible_token_price(price):
                weighted_price += price * liq
                weighted_liq += liq
                if liq > best_price_liq:
                    best_price_liq = liq
                    best_price = price
                    best_pair_chain = _normalize_dex_chain(p.get("chainId"))
        if vol and vol > 0:
            total_vol += vol
        if _is_plausible_token_price(price) and not best_price:
            best_price = price
            best_pair_chain = _normalize_dex_chain(p.get("chainId"))
        if mcap and mcap > best_mcap:
            best_mcap = mcap

    if weighted_liq > 0:
        best_price = weighted_price / weighted_liq
    if not best_pair_chain and pairs_to_use:
        best_pair_chain = _normalize_dex_chain(pairs_to_use[0].get("chainId"))

    # Volume spike detection
    vol_h1 = sum(float(p.get("volume", {}).get("h1", 0) or 0) for p in pairs_to_use)
    vol_h6 = sum(float(p.get("volume", {}).get("h6", 0) or 0) for p in pairs_to_use)
    volume_spike = False
    if vol_h6 > 0 and vol_h1 > 0:
        avg_per_hour = vol_h6 / 6
        if vol_h1 > _MAX_VOLUME_SPIKE_RATIO * avg_per_hour:
            volume_spike = True

    # Reserve checks
    min_reserve_base = 0
    min_reserve_quote = 0
    reserve_ok = True
    for p in pairs_to_use:
        liq_data = p.get("liquidity", {})
        base_res = float(liq_data.get("base", 0) or 0)
        quote_res = float(liq_data.get("quote", 0) or 0)
        if base_res > min_reserve_base:
            min_reserve_base = base_res
        if quote_res > min_reserve_quote:
            min_reserve_quote = quote_res
    if min_reserve_base < 1000 or min_reserve_quote < 1000:
        reserve_ok = False

    # Quality scoring
    score = 0
    checks = []

    # Check 1: Pair validation
    if pair_validated and validated_pairs:
        score += 3
        checks.append("pair_direct")
    elif pair_indirect and indirect_pairs:
        score += 1
        checks.append("pair_indirect")
    else:
        score -= 2
        checks.append("no_stable_pair")

    # Check 2: Liquidity + reserves
    if total_liq >= 100_000 and reserve_ok:
        score += 2
        checks.append("high_liq")
    elif total_liq >= _MIN_LIQUIDITY_USD and reserve_ok:
        score += 1
        checks.append("medium_liq")
    else:
        score -= 1
        checks.append("low_liq")

    # Check 3: Volume (penalize spikes)
    if total_vol >= 50_000 and not volume_spike:
        score += 2
        checks.append("high_vol_stable")
    elif total_vol >= _MIN_VOLUME_24H and not volume_spike:
        score += 1
        checks.append("medium_vol_stable")
    elif volume_spike:
        score -= 2
        checks.append("volume_spike")
    else:
        checks.append("low_vol")

    # Check 4: Distribution
    if top_holder_pct > 0 and top_holder_pct < _MAX_TOP_HOLDER_PCT:
        score += 1
        checks.append("good_dist")
    elif top_holder_pct >= _MAX_TOP_HOLDER_PCT:
        score -= 2
        checks.append("whale_risk")

    if chain_mismatch:
        score -= 3
        checks.append("chain_mismatch")

    # Confidence based on score
    if score >= 5 and pair_validated and not volume_spike:
        confidence = "high"
    elif score >= 2 and (pair_validated or pair_indirect):
        confidence = "medium"
    else:
        confidence = "low"

    result = {
        "dex_chain": best_pair_chain or requested_chain,
        "chain_mismatch": chain_mismatch,
        "price_usd": best_price,
        "liquidity_usd": total_liq,
        "volume_24h": total_vol,
        "market_cap": best_mcap,
        "confidence": confidence,
        "pair_validated": pair_validated,
        "top_holder_pct": top_holder_pct,
        "checks": checks,
    }
    _DEX_CACHE[cache_key] = (result, now)
    return result


def _get_token_age_days(chain: str, token_address: str) -> float | None:
    """Estimate token age from first tokentx. Returns days or None."""
    url = _etherscan_url(chain, "tokentx", contractaddress=token_address.lower())
    data = _etherscan_call(url)
    if data and data.get("status") == "1" and isinstance(data.get("result"), list):
        txs = data["result"]
        if txs:
            # Get oldest tx by sorting by blockNumber
            oldest = min(txs, key=lambda x: int(x.get("blockNumber", "99999999")))
            ts = oldest.get("timeStamp")
            if ts:
                try:
                    age_sec = time.time() - int(ts)
                    return age_sec / 86400
                except Exception:
                    pass
    return None


# # Covalent fallback 
def _covalent_balances(chain: str, address: str) -> list[dict[str, Any]]:
    """Fetch token balances via Covalent API. Returns list of {contract_address, symbol, decimals, balance, quote_usd}."""
    chain_id = _COVALENT_CHAINID.get(chain, "1")
    url = f"https://api.covalenthq.com/v1/{chain_id}/address/{address.lower()}/balances_v2/?key={_COVALENT_KEY}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("data", {}).get("items", [])
        results = []
        for item in items:
            bal_raw = item.get("balance", "0")
            dec = item.get("contract_decimals", 18)
            if not bal_raw or bal_raw == "0":
                continue
            try:
                bal_int = int(bal_raw)
            except Exception:
                continue
            if bal_int == 0:
                continue
            bal = bal_int / (10 ** dec)
            quote = item.get("quote")
            results.append({
                "contract_address": (item.get("contract_address") or "").lower(),
                "symbol": item.get("contract_ticker_symbol", "UNKNOWN"),
                "decimals": dec,
                "raw_balance": bal_int,
                "balance": bal,
                "quote_usd": quote,
            })
        return results
    except Exception:
        return []


# # Token detection 
def get_wallet_tokens(address: str, chain: str, blocks_back: int | None = None) -> list[str]:
    address = address.lower()
    # BSC: Etherscan V2 tokentx unreliable for BSC, use Covalent as primary
    if chain == "bsc":
        cov = _covalent_balances(chain, address)
        result = [t["contract_address"] for t in cov if t["contract_address"] and t["contract_address"] != "0x"]
        if result:
            return result[:10]
    # ETH: Etherscan tokentx as primary
    tx_list = _etherscan_tokentx(chain, address)
    token_counts: dict[str, int] = {}
    for tx in tx_list:
        contract = (tx.get("contractAddress") or "").lower()
        if contract and contract != "0x":
            token_counts[contract] = token_counts.get(contract, 0) + 1
    sorted_tokens = sorted(token_counts.keys(), key=lambda t: token_counts[t], reverse=True)
    result = sorted_tokens[:10]
    # Fallback: Covalent if Etherscan returned nothing
    if not result:
        cov = _covalent_balances(chain, address)
        result = [t["contract_address"] for t in cov if t["contract_address"] and t["contract_address"] != "0x"]
    return result


# # Token balances with quality filter 
def _get_cached_token_meta(token: str, chain: str) -> dict[str, Any] | None:
    conn = _get_db()
    row = conn.execute(
        "SELECT symbol, decimals, price_usd, liquidity_usd, volume_24h, confidence, pair_validated, top_holder_pct, age_days, last_updated FROM token_meta WHERE token_address=? AND chain=?",
        (token.lower(), chain)
    ).fetchone()
    conn.close()
    if row:
        return {
            "symbol": row[0], "decimals": row[1], "price_usd": row[2],
            "liquidity_usd": row[3], "volume_24h": row[4], "confidence": row[5],
            "pair_validated": bool(row[6]), "top_holder_pct": row[7], "age_days": row[8], "last_updated": row[9],
        }
    return None


def _set_cached_token_meta(token: str, chain: str, symbol: str, decimals: int, price_usd: float | None, liquidity_usd: float | None, volume_24h: float | None, confidence: str, pair_validated: bool = False, top_holder_pct: float = 0, age_days: float | None = None) -> None:
    conn = _get_db()
    conn.execute(
        """INSERT OR REPLACE INTO token_meta (token_address, chain, symbol, decimals, price_usd, liquidity_usd, volume_24h, confidence, pair_validated, top_holder_pct, age_days, last_updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (token.lower(), chain, symbol, decimals, price_usd, liquidity_usd, volume_24h, confidence, 1 if pair_validated else 0, top_holder_pct, age_days, time.time())
    )
    conn.commit()
    conn.close()


def _get_cached_wallet_token(wallet: str, chain: str, token: str) -> dict[str, Any] | None:
    conn = _get_db()
    row = conn.execute(
        "SELECT balance, value_usd, confidence, last_updated FROM wallet_token_cache WHERE wallet=? AND chain=? AND token_address=?",
        (wallet.lower(), chain, token.lower())
    ).fetchone()
    conn.close()
    if row and time.time() - row[3] < _CACHE_TTL:
        return {"balance": row[0], "value_usd": row[1], "confidence": row[2]}
    return None


def _set_cached_wallet_token(wallet: str, chain: str, token: str, balance: float, value_usd: float | None, confidence: str) -> None:
    conn = _get_db()
    conn.execute(
        """INSERT OR REPLACE INTO wallet_token_cache (wallet, chain, token_address, balance, value_usd, confidence, last_updated)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (wallet.lower(), chain, token.lower(), balance, value_usd, confidence, time.time())
    )
    conn.commit()
    conn.close()


def get_token_balances(address: str, tokens: list[str], chain: str) -> list[dict[str, Any]]:
    address = address.lower()
    results = []
    tx_list = _etherscan_tokentx(chain, address)
    metadata: dict[str, dict] = {}
    for tx in tx_list:
        c = (tx.get("contractAddress") or "").lower()
        if c and c not in metadata:
            metadata[c] = {
                "symbol": tx.get("tokenSymbol", ""),
                "decimals": int(tx.get("tokenDecimal", 18)),
            }

    # Pre-fetch Covalent fallback data if needed (BSC mainly)
    covalent_fallback: dict[str, dict] = {}
    if chain == "bsc":
        for citem in _covalent_balances(chain, address):
            addr = citem.get("contract_address", "").lower()
            if addr:
                covalent_fallback[addr] = citem

    for token in tokens[:30]:
        token = token.lower()
        try:
            source_trace: list[dict[str, Any]] = []
            contract_proof = _rpc_contract_proof(chain, token)
            source_trace.append(_source_item(
                "contract",
                contract_proof.get("rpc_source", "rpc"),
                chain,
                bool(contract_proof.get("exists")),
                f"eth_getCode bytes={contract_proof.get('bytecode_size', 0)}"
                + (f" error={contract_proof.get('error')}" if contract_proof.get("error") else ""),
            ))
            if not contract_proof.get("exists") and not contract_proof.get("error"):
                continue
            rpc_meta = _rpc_erc20_metadata(chain, token) if contract_proof.get("exists") else {}
            source_trace.append(_source_item(
                "metadata_rpc",
                rpc_meta.get("source", _RPC_SOURCE.get(chain, "rpc")),
                chain,
                bool(rpc_meta.get("ok")),
                f"symbol={rpc_meta.get('symbol') or '?'} decimals={rpc_meta.get('decimals') if rpc_meta.get('decimals') is not None else '?'}"
                + (f" supply={round(float(rpc_meta.get('total_supply') or 0), 4)}" if rpc_meta.get("total_supply") else "")
                + (f" errors={','.join(rpc_meta.get('errors') or [])}" if rpc_meta.get("errors") else ""),
            ))

            # 1. Get balance (Etherscan first, Covalent fallback)
            bal_res = _etherscan_tokenbalance(chain, token, address)
            raw_bal = None
            symbol = ""
            decimals = 18
            indexer_symbol = ""
            indexer_decimals = None
            covalent_value_usd = None
            balance_source = "none"
            metadata_source = "unknown"

            if bal_res and bal_res != "0":
                raw_bal = int(bal_res)
                meta = metadata.get(token, {})
                indexer_decimals = meta.get("decimals", 18)
                indexer_symbol = meta.get("symbol", "")
                decimals = int(rpc_meta.get("decimals") if rpc_meta.get("decimals") is not None else indexer_decimals)
                symbol = str(rpc_meta.get("symbol") or indexer_symbol or "")
                balance_source = "etherscan_v2"
                metadata_source = "rpc_eth_call+etherscan_tokentx" if rpc_meta.get("ok") and meta else ("rpc_eth_call" if rpc_meta.get("ok") else ("etherscan_tokentx" if meta else "default"))
            elif token in covalent_fallback:
                citem = covalent_fallback[token]
                raw_bal = int(citem.get("raw_balance") or int(citem["balance"] * (10 ** citem["decimals"])))
                indexer_decimals = citem["decimals"]
                indexer_symbol = citem["symbol"]
                decimals = int(rpc_meta.get("decimals") if rpc_meta.get("decimals") is not None else indexer_decimals)
                symbol = str(rpc_meta.get("symbol") or indexer_symbol or "")
                covalent_value_usd = citem.get("quote_usd")
                balance_source = "covalent_balances_v2"
                metadata_source = "rpc_eth_call+covalent_balances_v2" if rpc_meta.get("ok") else "covalent_balances_v2"

            if not raw_bal or raw_bal == 0:
                continue
            source_trace.append(_source_item("balance", balance_source, chain, True, "erc20 balance"))
            source_trace.append(_source_item("metadata", metadata_source, chain, bool(symbol), symbol or "symbol missing"))
            if rpc_meta.get("symbol") and indexer_symbol and str(rpc_meta["symbol"]).lower() != str(indexer_symbol).lower():
                source_trace.append(_source_item(
                    "source_mismatch",
                    "rpc_vs_indexer",
                    chain,
                    False,
                    f"symbol rpc={rpc_meta['symbol']} indexer={indexer_symbol}",
                ))
            if rpc_meta.get("decimals") is not None and indexer_decimals is not None and int(rpc_meta["decimals"]) != int(indexer_decimals):
                source_trace.append(_source_item(
                    "source_mismatch",
                    "rpc_vs_indexer",
                    chain,
                    False,
                    f"decimals rpc={rpc_meta['decimals']} indexer={indexer_decimals}",
                ))
            if decimals > 36 or decimals < 0:
                continue
            balance = raw_bal / (10 ** decimals)
            if balance < 0.000001:
                continue

            # 2. Check cache for quality data
            cached_meta = _get_cached_token_meta(token, chain)
            cached_wallet = _get_cached_wallet_token(address, chain, token)

            now = time.time()
            dex_data: dict[str, Any] = {}
            cached_meta_fresh = cached_meta and now - (cached_meta.get("last_updated") or 0) < _CACHE_TTL
            cached_meta_sane = bool(
                cached_meta_fresh
                and _is_plausible_token_price(cached_meta.get("price_usd"))
            )

            if cached_meta_sane:
                dex_data = {
                    "dex_chain": chain,
                    "chain_mismatch": False,
                    "price_usd": cached_meta.get("price_usd"),
                    "liquidity_usd": cached_meta.get("liquidity_usd"),
                    "volume_24h": cached_meta.get("volume_24h"),
                    "confidence": cached_meta.get("confidence"),
                    "pair_validated": cached_meta.get("pair_validated", False),
                    "top_holder_pct": cached_meta.get("top_holder_pct", 0),
                }
            else:
                # 3. Fetch from DexScreener
                dex_data = _get_dexscreener_data(token, chain)
            source_trace.append(_source_item(
                "market",
                "dexscreener_chain_scoped",
                dex_data.get("dex_chain") or chain,
                bool(dex_data.get("pair_validated")),
                ",".join(dex_data.get("checks") or []) or "no_checks",
            ))

            # 4. Check token age BEFORE caching
            age_days = _get_token_age_days(chain, token)
            source_trace.append(_source_item("age", "etherscan_v2_tokentx", chain, age_days is not None))
            if cached_meta_sane:
                pass
            else:
                _set_cached_token_meta(
                    token, chain, symbol, decimals,
                    dex_data.get("price_usd"),
                    dex_data.get("liquidity_usd"),
                    dex_data.get("volume_24h"),
                    dex_data.get("confidence", "low"),
                    dex_data.get("pair_validated", False),
                    dex_data.get("top_holder_pct", 0),
                    age_days,
                )

            confidence = dex_data.get("confidence", "low")
            explorer_chain = dex_data.get("dex_chain") or chain
            pair_validated = dex_data.get("pair_validated", False)
            top_holder_pct = dex_data.get("top_holder_pct", 0)
            price_usd = dex_data.get("price_usd")
            liquidity_usd = dex_data.get("liquidity_usd")
            if price_usd and not _is_plausible_token_price(price_usd):
                confidence = "low"
            if age_days is not None:
                if age_days < 1:
                    confidence = "low"  # Ignore brand new tokens
                elif age_days < _MIN_TOKEN_AGE_DAYS and confidence == "high":
                    confidence = "medium"  # Downgrade young tokens

            # 5. Downgrade if no validated pair
            if not pair_validated:
                if confidence == "high":
                    confidence = "medium"
                elif confidence == "medium":
                    confidence = "low"

            # 6. Downgrade if whale risk
            if top_holder_pct >= _MAX_TOP_HOLDER_PCT:
                confidence = "low"
            if dex_data.get("chain_mismatch"):
                confidence = "low"

            # 7. Fallback price from CoinGecko if DexScreener has no price but token is known
            if not price_usd and confidence in ("medium", "high"):
                cg_price = _get_coingecko_price(symbol.lower())
                if cg_price and cg_price > 0:
                    price_usd = cg_price
                    source_trace.append(_source_item("price_fallback", "coingecko_simple_price", chain, True, symbol.lower()))
            # 7b. Use Covalent quote_usd if still no price
            if not price_usd and covalent_value_usd and covalent_value_usd > 0 and balance > 0:
                price_usd = covalent_value_usd / balance
                source_trace.append(_source_item("price_fallback", "covalent_quote", chain, True))

            # 8. Compute value
            value_usd = None
            if price_usd and price_usd > 0:
                value_usd = round(balance * price_usd, 2)
            if value_usd:
                plausible = _is_plausible_wallet_value(value_usd, liquidity_usd)
                if plausible is False:
                    confidence = "low"
                elif plausible is None:
                    # Issue #271 : liquidité inconnue (API DexScreener en échec
                    # OU aucun pair) — on ne SAIT pas si la valeur est tenable.
                    # Avant, ce cas retournait True (plausible) et la valeur
                    # passait telle quelle. On dégrade à "low" : l'appelant
                    # filtre les "low" (étape 9), donc un token dont on ignore
                    # la liquidité ne peut plus s'afficher comme une position
                    # fiable. Fail-closed : l'ignorance ne vaut pas validation.
                    confidence = "low"

            # 9. Filter: ignore low confidence tokens entirely
            if confidence == "low":
                continue

            # 10. Filter: ignore tokens with value < $1
            if not value_usd or value_usd < _MIN_TOKEN_VALUE_USD:
                continue

            # 7. Cache wallet token
            _set_cached_wallet_token(address, chain, token, balance, value_usd, confidence)

            results.append({
                "token_address": token,
                "chain": chain,
                "explorer_chain": explorer_chain,
                "symbol": symbol,
                "decimals": decimals,
                "balance": round(balance, 6),
                "price_usd": price_usd,
                "value_usd": value_usd,
                "liquidity_usd": dex_data.get("liquidity_usd"),
                "volume_24h": dex_data.get("volume_24h"),
                "confidence": confidence,
                "pair_validated": pair_validated,
                "top_holder_pct": top_holder_pct,
                "age_days": age_days,
                "contract_verified_on_chain": bool(contract_proof.get("exists")),
                "contract_bytecode_size": contract_proof.get("bytecode_size", 0),
                "rpc_symbol": rpc_meta.get("symbol"),
                "rpc_decimals": rpc_meta.get("decimals"),
                "rpc_total_supply": rpc_meta.get("total_supply"),
                "rpc_total_supply_raw": rpc_meta.get("total_supply_raw"),
                "indexer_symbol": indexer_symbol,
                "indexer_decimals": indexer_decimals,
                "balance_source": balance_source,
                "metadata_source": metadata_source,
                "market_source": "dexscreener_chain_scoped",
                "source_trace": source_trace,
                "verified": confidence == "high" and pair_validated,
            })
        except Exception:
            continue

    return sorted(results, key=lambda x: x.get("value_usd") or 0, reverse=True)


# # CoinGecko fallback 
def _get_coingecko_price(coin_id: str) -> float | None:
    now = time.time()
    if coin_id in _PRICE_CACHE:
        p, ts = _PRICE_CACHE[coin_id]
        if now - ts < _PRICE_CACHE_TTL:
            return p
    try:
        sep = chr(38)
        url = f"https://api.coingecko.com/api/v3/simple/priceids={coin_id}{sep}vs_currencies=usd"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        p = data.get(coin_id, {}).get("usd")
        if p is not None:
            _PRICE_CACHE[coin_id] = (p, now)
            return p
    except Exception:
        pass
    return None


def compute_net_worth(native_balance: float, tokens: list[dict[str, Any]], chain: str) -> dict[str, Any]:
    native_coin = "binancecoin" if chain == "bsc" else "ethereum"
    native_price = _get_coingecko_price(native_coin)
    if not native_price:
        native_price = _get_native_price_usd(chain)
    if not native_price:
        native_price = 0.0
    native_usd = native_balance * native_price

    token_total = 0.0
    for t in tokens:
        conf = t.get("confidence", "low")
        val = t.get("value_usd")
        verified = t.get("verified", False)
        # Only count verified or medium+ tokens with value >= $1
        if conf in ("high", "medium") and val and val >= _MIN_TOKEN_VALUE_USD:
            token_total += val
        else:
            t["value_usd"] = None  # Mask value for excluded tokens

    net_worth = native_usd + token_total
    return {
        "native_balance": round(native_balance, 6),
        "native_value_usd": round(native_usd, 2),
        "tokens": tokens,
        "token_value_usd": round(token_total, 2),
        "net_worth_usd": round(net_worth, 2) if net_worth > 0 else None,
    }


# # Main analyzer 
def _etherscan_balance_native(chain: str, address: str) -> float:
    """Get native balance via Etherscan V2."""
    url = _etherscan_url(chain, "balance", address=address.lower())
    data = _etherscan_call(url)
    if data and data.get("status") == "1":
        try:
            return int(data.get("result", "0")) / 1e18
        except Exception:
            return 0.0
    return 0.0


def _etherscan_txcount_native(chain: str, address: str) -> int:
    """Get tx count via Etherscan V2 txlist."""
    url = _etherscan_url(chain, "txlist", address=address.lower())
    data = _etherscan_call(url)
    if data and data.get("status") == "1" and isinstance(data.get("result"), list):
        return len(data["result"])
    return 0


def _etherscan_txlist(chain: str, address: str) -> list[dict]:
    """Get full tx list via Etherscan V2."""
    url = _etherscan_url(chain, "txlist", address=address.lower())
    data = _etherscan_call(url)
    if data and data.get("status") == "1" and isinstance(data.get("result"), list):
        return data["result"]
    return []


def _covalent_transactions(chain: str, address: str) -> list[dict]:
    """Get transactions via Covalent (fallback for BSC)."""
    chain_id = _COVALENT_CHAINID.get(chain, "1")
    url = f"https://api.covalenthq.com/v1/{chain_id}/address/{address.lower()}/transactions_v2/?key={_COVALENT_KEY}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("data", {}).get("items", [])
        # Normalize to etherscan-like format
        result = []
        for item in items:
            ts = item.get("block_signed_at", "")
            ts_epoch = int(time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))) if ts else 0
            result.append({
                "timeStamp": str(ts_epoch),
                "from": item.get("from_address", "").lower(),
                "to": (item.get("to_address") or "").lower(),
                "value": str(item.get("value", 0)),
                "gasPrice": str(item.get("gas_price", 0)),
                "gasUsed": str(item.get("gas_spent", 0)),
                "isError": "0",
            })
        return result
    except Exception:
        return []


def _get_transactions(chain: str, address: str) -> list[dict]:
    """Get transactions, prefer Etherscan, fallback Covalent."""
    txs = _etherscan_txlist(chain, address)
    if txs:
        return txs
    return _covalent_transactions(chain, address)


# # Wallet Intelligence 
def compute_wallet_activity(txs: list[dict]) -> dict[str, Any]:
    """Compute activity metrics from tx list."""
    if not txs:
        return {"first_seen": None, "last_seen": None, "tx_count": 0, "active_days": 0, "tx_per_day": 0.0}

    timestamps = []
    days = set()
    for tx in txs:
        ts = tx.get("timeStamp")
        if ts:
            try:
                t = int(ts)
                timestamps.append(t)
                days.add(time.strftime("%Y-%m-%d", time.gmtime(t)))
            except Exception:
                pass

    if not timestamps:
        return {"first_seen": None, "last_seen": None, "tx_count": len(txs), "active_days": 0, "tx_per_day": 0.0}

    first_ts = min(timestamps)
    last_ts = max(timestamps)
    active_days = len(days)
    days_span = max(1, (last_ts - first_ts) / 86400)
    tx_per_day = len(txs) / days_span

    return {
        "first_seen": time.strftime("%Y-%m-%d", time.gmtime(first_ts)),
        "last_seen": time.strftime("%Y-%m-%d", time.gmtime(last_ts)),
        "tx_count": len(txs),
        "active_days": active_days,
        "tx_per_day": round(tx_per_day, 2),
    }


def compute_wallet_flow(txs: list[dict], address: str) -> dict[str, Any]:
    """Compute inflow/outflow from tx list."""
    address = address.lower()
    inflow = 0.0
    outflow = 0.0
    for tx in txs:
        if tx.get("isError") == "1":
            continue
        try:
            val = int(tx.get("value", "0")) / 1e18
        except Exception:
            continue
        from_addr = (tx.get("from") or "").lower()
        to_addr = (tx.get("to") or "").lower()
        if from_addr == address:
            outflow += val
        if to_addr == address:
            inflow += val
    return {
        "inflow_eth": round(inflow, 6),
        "outflow_eth": round(outflow, 6),
        "net_flow_eth": round(inflow - outflow, 6),
    }


def compute_token_concentration(tokens: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute token concentration metrics."""
    if not tokens:
        return {"top_token_pct": 0.0, "concentration_score": 0.0, "diversity_score": 0.0}

    total_value = sum(t.get("value_usd") or 0 for t in tokens)
    if total_value <= 0:
        return {"top_token_pct": 0.0, "concentration_score": 0.0, "diversity_score": 0.0}

    sorted_tokens = sorted(tokens, key=lambda x: x.get("value_usd") or 0, reverse=True)
    top_value = sorted_tokens[0].get("value_usd") or 0
    top_pct = (top_value / total_value) * 100

    # Herfindahl-style concentration (0 = perfectly diversified, 1 = single token)
    hhi = sum(((t.get("value_usd") or 0) / total_value) ** 2 for t in tokens)

    # Diversity: number of significant tokens (>00)
    significant = sum(1 for t in tokens if (t.get("value_usd") or 0) >= 100)

    return {
        "top_token_symbol": sorted_tokens[0].get("symbol", ""),
        "top_token_pct": round(top_pct, 1),
        "concentration_score": round(hhi, 3),
        "diversity_score": min(significant, 10),
    }


def compute_risk_score(tokens: list[dict[str, Any]], concentration: dict[str, Any], activity: dict[str, Any]) -> dict[str, Any]:
    """Compute risk score 0-100 (lower is safer)."""
    score = 20  # base
    reasons = []

    # Concentration risk
    if concentration.get("top_token_pct", 0) > 80:
        score += 25
        reasons.append("high_concentration")
    elif concentration.get("top_token_pct", 0) > 50:
        score += 15
        reasons.append("medium_concentration")

    # Low confidence tokens
    low_count = sum(1 for t in tokens if t.get("confidence") == "low")
    if low_count > 0:
        score += min(low_count * 5, 20)
        reasons.append("low_confidence_tokens")

    # New wallet
    if activity.get("tx_count", 0) < 5:
        score += 15
        reasons.append("new_wallet")

    # High frequency = potential bot
    if activity.get("tx_per_day", 0) > 50:
        score += 10
        reasons.append("high_frequency")

    # Whale risk
    total_value = sum(t.get("value_usd") or 0 for t in tokens)
    if total_value > 500000:
        score += 5
        reasons.append("whale_target")

    return {
        "score": min(score, 100),
        "level": "low" if score < 30 else "medium" if score < 60 else "high",
        "reasons": reasons,
    }


def compute_smart_label(tx_count: int, net_worth: float | None, token_count: int, activity: dict[str, Any], concentration: dict[str, Any]) -> str:
    """Compute intelligent wallet label."""
    if tx_count < 5:
        return "new_wallet"
    if net_worth and net_worth > 500000:
        return "whale"
    if tx_count > 1000 and activity.get("tx_per_day", 0) > 10:
        return "high_frequency"
    if token_count >= 5 and concentration.get("diversity_score", 0) >= 3:
        if net_worth and net_worth > 50000:
            return "smart_money"
    if tx_count > 100 and activity.get("active_days", 0) > 30:
        if token_count >= 3:
            return "active_trader"
    if net_worth and net_worth > 100000:
        return "whale"
    return "regular"


def analyze_wallet_full(address: str, chain: str = "bsc") -> dict[str, Any]:
    address = address.lower()

    # Native balance: Etherscan for ETH, RPC for BSC
    native_balance = 0.0
    if chain == "eth":
        native_balance = _etherscan_balance_native(chain, address)
    else:
        try:
            bal_res = _rpc_evm(chain, "eth_getBalance", [address, "latest"])
            native_balance = int(bal_res, 16) / 1e18 if bal_res else 0.0
        except Exception:
            native_balance = 0.0

    # TX count: Etherscan for ETH, RPC for BSC
    tx_count = 0
    if chain == "eth":
        tx_count = _etherscan_txcount_native(chain, address)
    else:
        try:
            tx_res = _rpc_evm(chain, "eth_getTransactionCount", [address, "latest"])
            tx_count = int(tx_res, 16) if tx_res else 0
        except Exception:
            tx_count = 0

    try:
        token_addrs = get_wallet_tokens(address, chain)
    except Exception:
        token_addrs = []

    try:
        tokens = get_token_balances(address, token_addrs, chain)
    except Exception:
        tokens = []

    worth = compute_net_worth(native_balance, tokens, chain)

    # Filter display tokens: only high/medium confidence with value >= $1
    display_tokens = [t for t in worth["tokens"] if t.get("confidence") in ("high", "medium") and t.get("value_usd") and t["value_usd"] >= _MIN_TOKEN_VALUE_USD]

    # Get full tx list for intelligence
    txs = _get_transactions(chain, address)
    activity = compute_wallet_activity(txs)
    flow = compute_wallet_flow(txs, address)
    concentration = compute_token_concentration(worth["tokens"])
    risk = compute_risk_score(worth["tokens"], concentration, activity)
    label = compute_smart_label(tx_count, worth["net_worth_usd"], len(worth["tokens"]), activity, concentration)

    # Build label reasons
    label_reasons = []
    if worth.get("net_worth_usd") and worth["net_worth_usd"] > 500000:
        label_reasons.append("high net worth")
    elif worth.get("net_worth_usd") and worth["net_worth_usd"] > 100000:
        label_reasons.append("significant holdings")
    if tx_count > 1000 and activity.get("tx_per_day", 0) > 10:
        label_reasons.append("high frequency trading")
    elif tx_count > 100 and activity.get("active_days", 0) > 30:
        label_reasons.append("sustained activity")
    if concentration.get("diversity_score", 0) >= 3 and len(worth["tokens"]) >= 5:
        label_reasons.append("diversified portfolio")
    if activity.get("tx_per_day", 0) > 5:
        label_reasons.append("active trader")
    if not label_reasons:
        label_reasons.append("regular wallet activity")

    return {
        "ok": True,
        "wallet": address,
        "chain": chain,
        "data_sources": {
            "rpc": {
                "chain": chain,
                "source": _RPC_SOURCE.get(chain, "unknown_rpc"),
                "methods": ["eth_getBalance", "eth_getTransactionCount", "eth_getCode", "eth_call"],
            },
            "balance_indexer": "etherscan_v2" if chain == "eth" else "covalent_balances_v2",
            "tx_indexer": "etherscan_v2_with_covalent_fallback",
            "market": "dexscreener_chain_scoped",
            "price_fallback": ["coingecko_simple_price", "covalent_quote"],
        },
        "native_balance": worth["native_balance"],
        "native_value_usd": worth["native_value_usd"],
        "tx_count": tx_count,
        "tokens": worth["tokens"],
        "display_tokens": display_tokens,
        "top_holdings": display_tokens[:5],
        "net_worth_usd": worth["net_worth_usd"],
        "wallet_label": label,
        "label_reasons": label_reasons,
        "token_count": len(worth["tokens"]),
        "tokens_with_value": len(display_tokens),
        "activity": activity,
        "flow": flow,
        "concentration": concentration,
        "risk_score": risk,
    }


__all__ = ["analyze_wallet_full", "get_wallet_tokens", "get_token_balances", "compute_net_worth"]
