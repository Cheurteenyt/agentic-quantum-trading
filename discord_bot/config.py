"""La config du bot Discord — lit .env à la racine du repo (stdlib, zéro dépendance).

Le .env est GITIGNORED (le token ne sort jamais). Les trois clés attendues :
  DISCORD_BOT_TOKEN     — le token du bot (portail développeur → Bot → Reset Token)
  DISCORD_GUILD_ID      — l'id du serveur (clic droit sur le serveur → Copier l'id,
                          mode développeur activé)
  DISCORD_HOME_CHANNEL  — l'id du salon où le bot poste les rapports (optionnel)
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_env() -> dict[str, str]:
    """Parse le .env (clé=valeur, # commentaires) — n'écrase pas l'environnement existant."""
    env: dict[str, str] = {}
    if not ENV_PATH.exists():
        return env
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            env[key] = value
    return env


_env = load_env()

DISCORD_BOT_TOKEN = _env.get("DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = _env.get("DISCORD_GUILD_ID") or os.environ.get("DISCORD_GUILD_ID", "")
DISCORD_HOME_CHANNEL = _env.get("DISCORD_HOME_CHANNEL") or os.environ.get("DISCORD_HOME_CHANNEL", "")

# La DB warehouse (lecture seule pour les commandes /status etc.)
KDB = ROOT / "data" / "warehouse" / "klines.db"
XPDB = ROOT / "data" / "warehouse" / "x_posts.db"


def validate() -> list[str]:
    """Les erreurs bloquantes lisibles — le bot refuse de démarrer autrement."""
    errs: list[str] = []
    if not DISCORD_BOT_TOKEN:
        errs.append("DISCORD_BOT_TOKEN vide — mets le token du bot dans .env "
                    "(portail développeur → Bot → Reset Token)")
    if not DISCORD_GUILD_ID:
        errs.append("DISCORD_GUILD_ID vide — l'id du serveur (clic droit → Copier l'id, "
                    "mode développeur activé dans Discord)")
    if DISCORD_GUILD_ID and not DISCORD_GUILD_ID.isdigit():
        errs.append("DISCORD_GUILD_ID doit être un nombre (l'id du serveur)")
    return errs
