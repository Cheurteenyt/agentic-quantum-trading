#!/usr/bin/env python3
"""Notifications Telegram du registre — le canal produit (alertes push).

Contrairement a l'ancien mecanisme Discord (token dans le .env Windows),
celui-ci lit la configuration du projet : backend/.env, cles
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID. Non configure = no-op silencieux
exit 0 : la chaine nocturne n'est JAMAIS bloquee par l'absence de config.

    python scripts/telegram_notify.py --message "..."
    python scripts/telegram_notify.py --file reports/registre-draft-post.txt

Setup utilisateur (une fois) :
  1. @BotFather sur Telegram -> /newbot -> token
  2. Ecrire un message au bot, puis lire https://api.telegram.org/bot<token>/getUpdates
     pour trouver son chat_id
  3. Renseigner TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID dans backend/.env
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "backend" / ".env"


def _load_env_keys() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_PATH.exists():
        return out
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def send_if_configured(text: str) -> bool:
    """Envoie le message. Retourne True si envoye ; no-op silencieux sinon."""
    env = _load_env_keys()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[telegram] non configure (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID "
              "absents de backend/.env) — skip silencieux")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(url, data=payload, timeout=15) as resp:
            body = json.loads(resp.read())
            if not body.get("ok"):
                print(f"[telegram] API refuse : {body}", file=sys.stderr)
                return False
            print("[telegram] message envoye")
            return True
    except Exception as exc:
        print(f"[telegram] erreur reseau : {type(exc).__name__} — skip", file=sys.stderr)
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Notification Telegram du registre")
    p.add_argument("--message")
    p.add_argument("--file")
    args = p.parse_args()
    text = args.message or ""
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    if not text.strip():
        p.print_help()
        return 2
    send_if_configured(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
