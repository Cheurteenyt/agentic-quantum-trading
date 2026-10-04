"""Le pont Bonsai-juge — le LLM local (127.0.0.1:8080) comme modérateur sémantique.

LA RÈGLE D'OR (design 05/10, non négociable) : un verdict Bonsai ne déclenche JAMAIS
un ban permanent seul — il propose ; l'humain clique dans #revue-secu.
Le serveur peut être arrêté par le watchdog d'inactivité : ensure_server le relance
(≈ 4 s, mmap).
"""
from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.request

LLAMA = "http://127.0.0.1:8080"

CLASSIFY_PROMPT = (
    "Tu es un modérateur de serveur crypto. Analyse ce message : `{message}`.\n"
    "Contexte : âge du compte {age} jours, salon #{channel}.\n"
    "Réponds en JSON strict et RIEN d'autre :\n"
    '{{"toxicity": 0-100, "scam_type": null|"airdrop"|"fake_support"|"pump_dump"'
    '|"impersonation"|"other", "confidence": 0.0-1.0, '
    '"action_suggested": "none"|"warn"|"mute"|"kick"|"ban"}}'
)


def _ensure_server(max_wait_s: int = 60) -> bool:
    try:
        with urllib.request.urlopen(LLAMA + "/health", timeout=3):
            return True
    except Exception:
        pass
    subprocess.run(["systemctl", "--user", "start", "bonsai-llama-server"],
                   capture_output=True, timeout=30)
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        time.sleep(2)
        try:
            with urllib.request.urlopen(LLAMA + "/health", timeout=3):
                return True
        except Exception:
            continue
    return False


def classify(message: str, age_days: float, channel: str) -> dict | None:
    """Le verdict sémantique — None si le juge est indisponible ou illisible."""
    if not _ensure_server():
        return None
    body = {
        "messages": [{"role": "user",
                      "content": CLASSIFY_PROMPT.format(message=message[:1500],
                                                        age=round(age_days, 1),
                                                        channel=channel)}],
        "max_tokens": 200,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(LLAMA + "/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            text = json.loads(r.read().decode())["choices"][0]["message"].get("content") or ""
    except Exception:
        return None
    # l'extraction du JSON : Bonsai peut l'entourer de texte
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if not m:
        return None
    try:
        verdict = json.loads(m.group(0))
        verdict["toxicity"] = int(verdict.get("toxicity") or 0)
        verdict["confidence"] = float(verdict.get("confidence") or 0.0)
        return verdict
    except (ValueError, TypeError):
        return None
