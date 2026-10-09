"""Écritures de fichiers porteurs de secrets : 0600 + atomique, jamais world-readable.

Doctrine (ronde 8) : un token écrit en 0644 (write_text sous umask 022)
est lisible par tout process local (backup, autre user, malware
opportuniste). Et les write_text non atomiques (truncate + write) peuvent
être lus DÉCHIRÉS par les lecteurs concurrents — le cache JWT fomo a 4
écrivains concurrents. mkstemp crée le fichier 0600 AVANT écriture :
aucune fenêtre où le secret est lisible par le monde, aucune lecture
déchirée (os.replace, même filesystem).

Modèle repris de discord_bot/dashboard.py (le seul os.chmod(0o600) du
repo, dont le tmp pré-rename était resté en 0644 — TOCTOU corrigé ici).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_secret(path: Path | str, data: str | bytes) -> None:
    """Écrit data dans path : tmp 0600 dans le même répertoire + os.replace.

    Le fichier final est 0600 quoi qu'il arrive (mkstemp), même s'il
    existait déjà en 0644 (rattrapage au premier refresh). Les lecteurs
    concurrents ne voient jamais d'état intermédiaire.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(p.parent), prefix=p.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data.encode("utf-8") if isinstance(data, str) else data)
        os.chmod(tmp_name, 0o600)  # mkstemp est déjà 0600 ; ceinture de bretelles
        os.replace(tmp_name, p)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
