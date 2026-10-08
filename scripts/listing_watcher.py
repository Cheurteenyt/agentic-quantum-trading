#!/usr/bin/env python
"""Détecteur de nouveaux listings Aster — attraper les coins le jour J.

La thèse memecoin vit ici : MEMEUSDT a été listé sur Aster il y a 2 semaines
sans que personne ne le remarque dans nos outils. Ce script compare
l'exchangeInfo live à l'univers connu (snapshot local) et à chaque nouveau
perp TRADING : l'inscrit, fetch ses premières bougies, le signale au Pulse
et au registre (nouvelles recherches X possibles).

Usage :
  .venv/bin/python scripts/listing_watcher.py            # détecte + rapporte
  .venv/bin/python scripts/listing_watcher.py --init     # initialise le snapshot
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "warehouse" / "aster_universe.json"
EXCHANGEINFO = "https://fapi.asterdex.com/fapi/v1/exchangeInfo"
KNOWN_MEMES = ("MEME", "BOME", "PEPE", "WIF", "BONK", "FLOKI", "PNUT", "MOODENG",
               "NEIRO", "TURBO", "PENGU", "NOT", "DOGS", "TRUMP", "FARTCOIN",
               "CATE", "DOG", "CAT", "PUMP", "SOL", "AI", "BABY")


def live_universe() -> dict[str, dict]:
    req = urllib.request.Request(EXCHANGEINFO, headers={"User-Agent": "trading-agent/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.load(resp)
    return {
        s["symbol"]: {"onboardDate": s.get("onboardDate"), "status": s.get("status")}
        for s in d.get("symbols", [])
        if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"
    }


def _write_atomic(path: Path, text: str) -> None:
    """FIX R3 (C-D2) : écriture atomique tmp + os.replace. Le write_text
    direct laissait un JSON TRONQUÉ si le processus mourait pendant l'écriture
    (TimeoutStartSec, OOM, mount externe) — et le watcher se re-snapshottait
    impossible : JSONDecodeError au tir suivant, toutes les nuits jusqu'à
    intervention manuelle (empoisonnement auto-entretenu du nocturne).
    Même patron que refresh_aster_cache.write_cache_atomic."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    p = argparse.ArgumentParser(description="Détecteur de nouveaux listings Aster")
    p.add_argument("--init", action="store_true", help="enregistrer l'univers actuel comme référence")
    args = p.parse_args()

    # FIX R3 (C-D1) : cette étape est ExecStart= BLOQUANTE (l.35 du nocturne) :
    # un hic réseau sur exchangeInfo (URLError, timeout, 5xx, 429) levait un
    # traceback non attrapé → exit 1 → les 26 étapes suivantes (lcs, regime,
    # anti_liq, portfolio_sim, stacked, the_machine, campagne…) sautées.
    # Un watcher de listings n'a pas vocation à couper le pipeline.
    try:
        current = live_universe()
    except Exception as exc:  # noqa: BLE001
        print(f"[watcher] exchangeInfo indisponible, nuit dégradée : {exc}",
              file=sys.stderr)
        return 0
    now = time.time()

    if args.init or not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(SNAPSHOT, json.dumps({"captured_at": now, "symbols": current}, indent=1))
        print(f"[watcher] snapshot initial : {len(current)} perps USDT TRADING")
        return 0

    # FIX R3 (C-D2) : un snapshot tronqué (kill pendant écriture) levait
    # JSONDecodeError → exit 1 chaque nuit suivante. Re-snapshot et on continue.
    try:
        known = json.loads(SNAPSHOT.read_text()).get("symbols", {})
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("[watcher] snapshot corrompu — re-snapshot complet", file=sys.stderr)
        _write_atomic(SNAPSHOT, json.dumps({"captured_at": now, "symbols": current}, indent=1))
        return 0
    added = sorted(set(current) - set(known))
    removed = sorted(set(known) - set(current))

    lines = [f"# Nouveaux listings Aster — {datetime.now(tz=timezone.utc):%d/%m/%Y %H:%M} UTC", ""]
    if added:
        lines.append("## Nouveaux perps USDT (TRADING)")
        lines.append("")
        for sym in added:
            onboard = current[sym].get("onboardDate")
            is_meme = any(sym.startswith(m) for m in KNOWN_MEMES)
            tag = " — **profil memecoin**" if is_meme else ""
            lines.append(f"- `{sym}` (onboard {onboard}){tag}")
            # fetch immédiat des premières bougies 1h pour le futur backtest
            try:
                subprocess.run(
                    [str(ROOT / ".venv" / "bin" / "python"),
                     str(ROOT / "scripts" / "fetch_klines.py"),
                     "--fetch-range", sym, "--target-bars", "2000"],
                    capture_output=True, timeout=120, check=False,
                )
                lines.append(f"  - klines 1h fetchées (warehouse)")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"  - klines non fetchées : {exc}")
        lines.append("")
    if removed:
        lines += ["## Retirés (delisting ?)", ""] + [f"- `{s}`" for s in removed] + [""]
    if not added and not removed:
        lines.append(f"Aucun changement ({len(current)} perps stables).")

    out = ROOT / "reports" / "listings-watch.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write_atomic(SNAPSHOT, json.dumps({"captured_at": now, "symbols": current}, indent=1))
    print(f"[watcher] +{len(added)} -{len(removed)} -> {out}")
    for sym in added:
        print(f"  NOUVEAU: {sym}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
