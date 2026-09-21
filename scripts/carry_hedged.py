#!/usr/bin/env python3
"""Carry intra-Aster — paires de perps qui se compensent (100 % Aster).

Contrainte utilisateur (2026-09-21) : AUCUN trade sur un autre exchange.
Donc pas de jambe spot Binance : le carry se construit DANS Aster :

  short le perp a funding tres positif (les shorts encaissent)
  + long le perp a funding negatif (les longs encaissent)
  = les deux jambes encaissent du funding, et le risque de prix ne porte
    que sur l'ECART entre les deux actifs — pas sur le marche.

La neutralite depend de la CORRELATION entre les deux jambes : mesuree
sur les bougies 1h reelles (7 derniers jours, endpoint public Aster).

  corr >= 0.70  -> quasi-neutre
  0.40 - 0.70   -> correlation partielle (risque residuel reel)
  < 0.40        -> pas un hedge, juste deux positions opposees

Limites affichees : le funding varie a chaque reglement de 8 h, la
correlation n'est pas une garantie (les crises cassent les correlations),
deux jambes = deux gestions de marge.

    python scripts/carry_hedged.py
"""
from __future__ import annotations

import json
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "backend" / "services" / "onchain" / "aster" / \
    "aster_public_funding_history_cache.json"
REPORTS = ROOT / "reports"

BASE_URL = "https://fapi.asterdex.com"
USER_AGENT = "trading-agent-carry/1.0 (stdlib urllib)"
BPS_PER_8H_TO_ANNUAL_PCT = 3 * 365 / 100
N_SHORTS = 6          # meilleures jambes courtes (funding positif)
N_LONGS = 4           # meilleures jambes longues (funding negatif)
KLINE_LIMIT = 168     # 7 jours de bougies 1h
CORR_QUASI_NEUTRE = 0.70
CORR_PARTIELLE = 0.40


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _ann_pct(bps_per_8h: float | None) -> float | None:
    return bps_per_8h * BPS_PER_8H_TO_ANNUAL_PCT if bps_per_8h else None


def funding_sides() -> tuple[list[dict], list[dict]]:
    """Jambes courtes (funding positif, shorts encaissent) et longues
    (funding negatif, longs encaissent), triees par annualise."""
    with CACHE.open(encoding="utf-8") as fh:
        cache = json.load(fh)
    shorts: list[dict] = []
    longs: list[dict] = []
    for sym, entry in cache.get("symbols", {}).items():
        data = entry.get("data") or {}
        ann = _ann_pct(data.get("latest_funding_bps_per_8h"))
        if ann is None:
            continue
        row = {"symbol": sym, "ann": ann}
        (shorts if ann > 0 else longs).append(row)
    shorts.sort(key=lambda r: r["ann"], reverse=True)
    longs.sort(key=lambda r: r["ann"])  # le plus negatif d'abord
    return shorts[:N_SHORTS], longs[:N_LONGS]


def hourly_returns(symbol: str) -> list[float] | None:
    """Rendements horaires sur les 7 derniers jours (endpoint public Aster)."""
    try:
        raw = _get_json(
            f"{BASE_URL}/fapi/v3/klines?symbol={symbol}&interval=1h"
            f"&limit={KLINE_LIMIT}"
        )
        closes = [float(row[4]) for row in raw]
        if len(closes) < 50:
            return None
        return [
            (b - a) / a for a, b in zip(closes, closes[1:])
        ]
    except Exception:
        return None


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 30:
        return None
    xs, ys = xs[-n:], ys[-n:]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs) ** 0.5
    vy = sum((y - my) ** 2 for y in ys) ** 0.5
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def build_pairs() -> list[dict]:
    shorts, longs = funding_sides()
    if not shorts or not longs:
        return []
    returns_cache: dict[str, list[float] | None] = {}
    for row in shorts + longs:
        returns_cache[row["symbol"]] = hourly_returns(row["symbol"])
    pairs: list[dict] = []
    for s in shorts:
        for l in longs:
            rs, rl = returns_cache.get(s["symbol"]), returns_cache.get(l["symbol"])
            if not rs or not rl:
                corr = None
            else:
                corr = pearson(rs, rl)
            pairs.append({
                "short_leg": s["symbol"],
                "long_leg": l["symbol"],
                "net_ann": s["ann"] + abs(l["ann"]),
                "corr": corr,
            })
    pairs.sort(key=lambda p: (p["corr"] is not None and p["corr"] >= CORR_QUASI_NEUTRE,
                              p["corr"] if p["corr"] is not None else 0,
                              p["net_ann"]), reverse=True)
    return pairs


def _label(corr: float | None) -> str:
    if corr is None:
        return "correlation inconnue"
    if corr >= CORR_QUASI_NEUTRE:
        return "quasi-neutre"
    if corr >= CORR_PARTIELLE:
        return "correlation partielle"
    return "pas un hedge"


def write_report(pairs: list[dict], n_shorts: int, n_longs: int) -> Path:
    now = _utc_now()
    lines = [
        "# Carry intra-Aster — paires de perps qui se compensent",
        "",
        f"Genere : {now} UTC — 100 % Aster (contrainte utilisateur : aucun",
        "autre exchange). Jambes : funding du DERNIER reglement, annualise.",
        "",
        f"Jambes courtes candidates : {n_shorts} | jambes longues : {n_longs}",
        "",
        "| short (encaisse) | long (encaisse) | carry net ann. | correlation | lecture |",
        "|---|---|---|---|---|",
    ]
    for p in pairs:
        corr = f"{p['corr']:.2f}" if p["corr"] is not None else "?"
        lines.append(
            f"| {p['short_leg']} | {p['long_leg']} | {p['net_ann']:+.1f} % "
            f"| {corr} | {_label(p['corr'])} |"
        )
    if not pairs:
        lines.append("| — | — | — | — | aucune jambe long collectrice ce soir |")
    lines += [
        "",
        "## Regle de lecture",
        "",
        "Seules les paires 'quasi-neutres' (corr >= 0.70) se defendent comme",
        "des carries. 'Correlation partielle' = du risque residuel reel.",
        "'Pas un hedge' = deux paris opposes deguises en arbitrage.",
        "Le funding varie a chaque reglement de 8 h ; les crises cassent les",
        "correlations ; deux jambes = deux gestions de marge. Le carry range,",
        "il ne conseille pas.",
    ]
    out = REPORTS / f"carry-intra-aster-{now.replace(':', '').replace('-', '')}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (REPORTS / "carry-intra-aster.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return out


def main() -> int:
    shorts, longs = funding_sides()
    if not shorts or not longs:
        print("[carry] pas de paire possible ce soir "
              f"({len(shorts)} shorts / {len(longs)} longs collecteurs)",
              file=sys.stderr)
        return 1
    pairs = build_pairs()
    out = write_report(pairs, len(shorts), len(longs))
    print(f"[carry] {len(pairs)} paires — rapport : {out}")
    for p in pairs[:5]:
        corr = f"{p['corr']:.2f}" if p["corr"] is not None else "?"
        print(f"  short {p['short_leg']:16} + long {p['long_leg']:16} "
              f"carry {p['net_ann']:+.1f} %/an | corr {corr} | {_label(p['corr'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
