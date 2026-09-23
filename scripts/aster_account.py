#!/usr/bin/env python
"""Sonde du compte Aster V3 — signature EIP-712 (modèle officiel api-docs).

Lit .env : ASTER_WALLET_ADDRESS (user), ASTER_API_KEY (signer),
ASTER_API_PRIVATE_KEY (clé privée de l'API wallet).
Interroge GET /fapi/v3/balance sur fapi.asterdex.com (fapi3 est bloqué par
le WAF depuis notre client) et affiche les soldes non nuls.
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_typed_data

ROOT = Path(__file__).resolve().parents[1]
HOST = "https://fapi.asterdex.com"  # fapi3 est bloqué par WAF depuis ici

TYPED_DATA = {
    "types": {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Message": [{"name": "msg", "type": "string"}],
    },
    "primaryType": "Message",
    "domain": {
        "name": "AsterSignTransaction",
        "version": "1",
        "chainId": 1666,
        "verifyingContract": "0x0000000000000000000000000000000000000000",
    },
    "message": {"msg": ""},
}

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "PythonApp/1.0",
}


def load_env() -> dict[str, str]:
    vals: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            vals[k.strip()] = v.replace("\ufeff", "").lstrip("=").strip()
    return vals


def sign_params(params: dict, signer: str, private_key: str) -> str:
    nonce = str(math.trunc(time.time() * 1_000_000))
    p = dict(params)
    p["nonce"] = str(nonce)
    p["signer"] = signer
    qs = urllib.parse.urlencode(p)
    typed = json.loads(json.dumps(TYPED_DATA))
    typed["message"]["msg"] = qs
    # eth-account récent : encode_typed_data(domain, primary_type, message_types→ full)
    message = encode_typed_data(
        full_message={"types": typed["types"], "primaryType": typed["primaryType"],
                      "domain": typed["domain"], "message": typed["message"]})
    signed = Account.sign_message(message, private_key=private_key)
    return qs + "&signature=" + signed.signature.hex()


def get_signed(path: str, params: dict, user: str, signer: str,
               private_key: str) -> dict | list:
    p = dict(params)
    p["user"] = user
    qs = sign_params(p, signer, private_key)
    url = f"{HOST}{path}?{qs}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main() -> int:
    vals = load_env()
    user = vals.get("ASTER_WALLET_ADDRESS", "")
    signer = vals.get("ASTER_API_KEY", "")
    pk = vals.get("ASTER_API_PRIVATE_KEY", "")
    missing = [n for n, v in (("ASTER_WALLET_ADDRESS", user),
                              ("ASTER_API_KEY", signer),
                              ("ASTER_API_PRIVATE_KEY", pk)) if not v]
    if missing:
        print(f"champs manquants dans .env : {missing}", file=sys.stderr)
        return 1
    try:
        data = get_signed("/fapi/v3/balance", {}, user, signer, pk)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} : {e.read()[:300]}", file=sys.stderr)
        return 1
    if isinstance(data, dict) and "code" in data:
        print(f"erreur API : {data}", file=sys.stderr)
        return 1
    nz = [b for b in data if float(b.get("balance", 0)) != 0]
    print(f"compte lisible : {len(data)} actifs, {len(nz)} non nuls")
    for b in nz[:12]:
        print(f"  {b['asset']}: {float(b['balance']):,.4f} "
              f"(dispo {float(b['availableBalance']):,.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
