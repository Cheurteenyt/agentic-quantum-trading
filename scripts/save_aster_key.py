#!/usr/bin/env python
"""Enregistre la clé API Aster dans .env — saisie INVISIBLE (getpass).

Lancé dans un terminal : colle la clé, Entrée, colle le secret, Entrée.
Rien ne s'affiche à l'écran, rien ne va dans l'historique du shell.
"""
from __future__ import annotations

import getpass
import os
import re
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


# FIX ronde 8 : le log vivait dans un dossier temporaire partagé
# (world-readable, nom prédictible, open("a") suit les symlinks) et
# journalisait le DÉBUT de la clé — un préfixe de secret + un fichier
# suivable par n'importe quel process local, c'est une fuite en 2 lignes.
# Log désormais sous data/ (git-ignoré, répertoire privé), créé 0600,
# O_NOFOLLOW, et SANS aucun fragment de clé.
LOG = ROOT / "data" / "save_key.log"


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def main() -> int:
    fields = [("ASTER_WALLET_ADDRESS", "Adresse de ton portefeuille (0x...)"),
              ("ASTER_API_KEY", "Ta clé api Aster (telle qu'affichée)")]
    print("Saisie invisible — colle puis Entrée pour chaque champ.")
    log("=== nouvelle tentative ===")
    values = {}
    for k, label in fields:
        v = getpass.getpass(f"{label} : ").strip()
        # JAMAIS de fragment de la valeur dans le log (diagnostic = présence + taille)
        log(f"{k} : ok, {len(v)} caractères")
        values[k] = v
    missing = [k for k, v in values.items() if not v]
    if missing:
        print(f"ERREUR : champs vides : {missing}", file=sys.stderr)
        return 1
    src = ENV.read_text()
    for k, v in values.items():
        src = re.sub(rf"(?m)^{k}=.*$", f"{k}={v}", src)
    ENV.write_text(src)
    ok = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            if k.strip() in values:
                ok[k.strip()] = bool(v.strip())
    if all(ok.values()):
        print("✓ enregistré et vérifié — rien n'a été affiché.")
        log("succès : les 2 valeurs enregistrées")
        return 0
    log("échec : vérification finale échouée")
    print(f"ERREUR : vérification échouée (détails dans {LOG})",
          file=sys.stderr)
    return 1
