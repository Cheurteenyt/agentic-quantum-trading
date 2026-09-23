#!/usr/bin/env python
"""Enregistre la clé API Aster dans .env — saisie INVISIBLE (getpass).

Lancé dans un terminal : colle la clé, Entrée, colle le secret, Entrée.
Rien ne s'affiche à l'écran, rien ne va dans l'historique du shell.
"""
from __future__ import annotations

import getpass
import re
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


LOG = Path("/tmp/save_key.log")

def log(msg: str) -> None:
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def main() -> int:
    fields = [("ASTER_WALLET_ADDRESS", "Adresse de ton portefeuille (0x...)"),
              ("ASTER_API_KEY", "Ta clé api Aster (telle qu'affichée)")]
    print("Saisie invisible — colle puis Entrée pour chaque champ.")
    log("=== nouvelle tentative ===")
    values = {}
    for k, label in fields:
        v = getpass.getpass(f"{label} : ").strip()
        log(f"{k} : {len(v)} caractères, début={v[:6]!r}")
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
    print("ERREUR : vérification échouée (détails dans /tmp/save_key.log)",
          file=sys.stderr)
    return 1
