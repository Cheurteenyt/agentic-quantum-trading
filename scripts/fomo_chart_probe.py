#!/usr/bin/env python
"""LA SONDE DE CHART fomo — identifier la source de données du graphique.

L'app fomo.family est une SPA : son chart de prix vient d'un endpoint API
(XHR/fetch). Si on l'identifie, on peut récolter L'HISTORIQUE COMPLET des
tokens immédiatement (au lieu d'attendre des semaines de snapshots).

La méthode : se connecter au daemon CDP :9222 (la session fomo persistée),
ouvrir fomo.family, CAPTURER toutes les réponses réseau pendant que l'app
tourne, et filtrer ce qui ressemble à des données de prix/candles.

  .venv/bin/python scripts/fomo_chart_probe.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fomo_harvest import _connect_cdp, BASE  # noqa: E402

PATTERNS = ("candle", "kline", "chart", "history", "price", "token",
            "market", "bonding", "trade", "ohlcv")


def main() -> int:
    pw, browser = _connect_cdp()
    if browser is None:
        print("[probe] le daemon fomo ne répond pas sur :9222")
        return 1
    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        seen: dict[str, str] = {}       # url → le corps (tronqué)

        def on_response(resp):
            url = resp.url
            low = url.lower()
            if not any(p in low for p in PATTERNS):
                return
            if any(x in low for x in (".js", ".css", ".png", ".svg", ".woff",
                                      ".ico", "sentry", "analytics")):
                return
            try:
                body = resp.text()
            except Exception:
                return
            if len(body) > 200 and any(c.isdigit() for c in body[:500]):
                seen[url] = body[:4000]

        page.on("response", on_response)
        page.goto(BASE, timeout=30000, wait_until="domcontentloaded")
        time.sleep(18)                   # laisser l'app charger ses données
        page.close()

        print(f"[probe] {len(seen)} endpoints candidats capturés :")
        for url, body in list(seen.items())[:14]:
            print(f"  {url[:140]}")
            print(f"    corps: {body[:180].replace(chr(10), ' ')}")
        out = ROOT / "data" / "fomo" / "chart_probe.json"
        out.write_text(json.dumps(seen, indent=1, ensure_ascii=False))
        print(f"[probe] dump complet : {out}")
        return 0
    finally:
        pw.stop()


if __name__ == "__main__":
    raise SystemExit(main())
