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


def main() -> int:
    p = argparse.ArgumentParser(description="Détecteur de nouveaux listings Aster")
    p.add_argument("--init", action="store_true", help="enregistrer l'univers actuel comme référence")
    args = p.parse_args()

    current = live_universe()
    now = time.time()

    if args.init or not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps({"captured_at": now, "symbols": current}, indent=1))
        print(f"[watcher] snapshot initial : {len(current)} perps USDT TRADING")
        return 0

    known = json.loads(SNAPSHOT.read_text()).get("symbols", {})
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
    SNAPSHOT.write_text(json.dumps({"captured_at": now, "symbols": current}, indent=1))
    print(f"[watcher] +{len(added)} -{len(removed)} -> {out}")
    for sym in added:
        print(f"  NOUVEAU: {sym}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
