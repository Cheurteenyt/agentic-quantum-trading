#!/usr/bin/env python
"""Rotation cashtag X — couvrir TOUT l'univers suivi, 4 tickers par nuit.

Univers = memecoins suivis + nouveaux coins fomo (graduated/bonding, 3 jours)
+ tickers d'ondes (wave_flags), hors majeurs déjà couverts chaque nuit.
La rotation par jour garantit une couverture complète en len(univers)/4 nuits
— un coin n'échappe plus au registre parce qu'il n'est pas BTC.

Usage :
  .venv/bin/python scripts/x_rotation.py            # lot du jour
  .venv/bin/python scripts/x_rotation.py --list     # voir le lot sans pêcher
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"
MAJEURS = {"BTC", "ETH", "SOL", "ASTER", "XRP", "BNB", "DOGE", "ADA", "AVAX",
           "LINK", "LTC", "1000PEPE"}  # 1000PEPE = alias de couverture PEPE


def _memecoins() -> set[str]:
    try:
        from scripts.memecoin_pulse import MEMECOINS
        return {t.upper() for t in MEMECOINS}
    except Exception:  # noqa: BLE001
        return set()


def _fomo_new(days: int = 3) -> set[str]:
    """Coins récents de la couche découverte fomo (graduated + bonding)."""
    out: set[str] = set()
    try:
        con = sqlite3.connect(FOMO_DB)
        cutoff = time.time() - days * 86400
        for (t,) in con.execute(
            "SELECT DISTINCT ticker FROM fomo_new_coins "
            "WHERE captured_at > ? AND tab IN ('graduated','bonding')",
            (cutoff,)):
            if t and len(t) <= 12:
                out.add(t.upper())
        con.close()
    except Exception:  # noqa: BLE001
        pass
    return out


def _waves() -> set[str]:
    out: set[str] = set()
    try:
        con = sqlite3.connect(FOMO_DB)
        for (t,) in con.execute("SELECT DISTINCT ticker FROM wave_flags"):
            out.add(t.upper())
        con.close()
    except Exception:  # noqa: BLE001
        pass
    return out


def lot_du_jour(per_run: int = 4) -> list[str]:
    raw = (_memecoins() | _fomo_new() | _waves()) - MAJEURS
    uni = sorted({(t[:-4] if t.endswith("USDT") else t) for t in raw if t} - {""})
    if not uni:
        return []
    day = int(time.time() // 86400)
    n_batches = max(1, (len(uni) + per_run - 1) // per_run)
    start = (day % n_batches) * per_run
    return uni[start:start + per_run]


def main() -> int:
    ap = argparse.ArgumentParser(description="Rotation cashtag X nocturne")
    ap.add_argument("--list", action="store_true", help="affiche le lot sans pêcher")
    ap.add_argument("--scrolls", type=int, default=2)
    args = ap.parse_args()

    batch = lot_du_jour()
    raw = (_memecoins() | _fomo_new() | _waves()) - MAJEURS
    uni = sorted({(t[:-4] if t.endswith("USDT") else t) for t in raw if t} - {""})
    print(f"[rotation] univers {len(uni)} tickers — lot du jour : {batch}",
          file=sys.stderr)
    if not batch:
        return 1
    if args.list:
        return 0

    queries = ",".join(f"${t}" for t in batch)
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "x_harvest.py"),
         "--searches", queries, "--scrolls", str(args.scrolls)],
        cwd=ROOT, timeout=900)
    if r.returncode != 0:
        print("[rotation] x_harvest a échoué", file=sys.stderr)
        return 1
    out = ROOT / "data" / "x_harvest" / "latest-searches.json"
    if not out.exists():
        print("[rotation] pas de sortie x_harvest", file=sys.stderr)
        return 1
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "fetch_x_posts.py"),
         "--ingest-json", "data/x_harvest/latest-searches.json",
         "--query", "rotation"],
        cwd=ROOT, timeout=300)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
