#!/usr/bin/env python
"""Backtest du signal Absorption & Sweep sur perps Aster — étude d'événements.

Le signal vient de nos indicateurs (MMT rev 5 + aster_absorption.py) : mêmes
règles EXACTES (delta extrême + corps faible = absorption ; perforation ATR
+ reclaim = sweep). Ce script fetch les klines AVEC taker-buy (le warehouse
ne stocke pas le split), rejoue le détecteur sur ~3000 bougies 1h et mesure
les rendements forward directionnels après chaque événement.

Discipline pré-enregistrée (annoncée AVANT de voir les résultats) :
  - verdict par (type d'événement × horizon) : N >= 10 ET winrate >= 55 %
    => « prometteur (à confirmer) » ; N >= 10 ET < 55 % => bruit ; sinon insuffisant
  - split 70/30 : train (70 % les plus anciennes) / val (30 % les plus récentes)
  - coûts : 2 x frais taker (USDT 4 bps) = 8 bps par aller-retour ; slippage
    NON inclus (le spread historique n'est pas mesurable rétroactivement)
  - multiplicité : ~4 types x 3 horizons x N symboles = beaucoup de tirages —
    un seul survivant sur 20 est attendu par hasard. Le rapport le rappelle.

Usage :
  .venv/bin/python scripts/backtest_absorption.py
  .venv/bin/python scripts/backtest_absorption.py --symbols BTCUSDT,WIFUSDT --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aster_absorption import bars_from_klines, detect  # noqa: E402

KLINES_URL = "https://fapi.asterdex.com/fapi/v1/klines"
FEE_BPS_USDT = 4.0          # taker par jambe (legacy aster_perps_model)
COST_BPS = 2 * FEE_BPS_USDT  # aller-retour
HORIZONS_H = {"+1h": 1, "+4h": 4, "+12h": 12}
TRAIN_FRAC = 0.70

DEFAULT_SYMBOLS = [
    # majors
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
    # memecoins (historique suffisant)
    "BOMEUSDT", "WIFUSDT", "PNUTUSDT", "MOODENGUSDT", "NEIROUSDT",
    "TURBOUSDT", "PENGUUSDT", "NOTUSDT", "DOGSUSDT", "TRUMPUSDT",
    "FARTCOINUSDT", "1000PEPEUSDT", "DRAMUSDT", "PIEVERSEUSDT",
    # champions legacy
    "LABUSDT", "HYPEUSDT", "HUSDT",
]
MIN_BARS = 800

DIRECTION = {
    "absorption_buy": 1, "sweep_low": 1,
    "absorption_sell": -1, "sweep_high": -1,
}


def fetch_klines_paged(symbol: str, interval: str, target: int = 3000) -> list:
    """Klines avec taker-buy, paginé vers l'arrière (limite API 1500/page)."""
    out: list = []
    end_ms: int | None = None
    while len(out) < target:
        limit = min(1500, target - len(out))
        url = f"{KLINES_URL}?symbol={symbol}&interval={interval}&limit={limit}"
        if end_ms is not None:
            url += f"&endTime={end_ms}"
        req = urllib.request.Request(url, headers={"User-Agent": "trading-agent/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            batch = json.load(resp)
        if not batch:
            break
        out = batch + out
        end_ms = int(batch[0][0]) - 1
        if len(batch) < limit:
            break
        time.sleep(0.25)  # rate limiting poli
    return out


def forward_returns(bars: list[dict], events: list[dict]) -> list[dict]:
    """Rendements directionnels (nets de frais) aux horizons, par événement."""
    results = []
    closes = [b["c"] for b in bars]
    for ev in events:
        i = ev["i"]
        sign = DIRECTION[ev["kind"]]
        row = {"kind": ev["kind"], "i": i, "side": "long" if sign > 0 else "short"}
        for label, h in HORIZONS_H.items():
            j = i + h
            row[label] = None if j >= len(closes) else sign * (closes[j] / closes[i] - 1) * 1e4 - COST_BPS
        results.append(row)
    return results


def verdict_of(n: int, wr: float | None) -> str:
    if n < 10:
        return "INSUFFISANT"
    if wr is not None and wr >= 55.0:
        return "PROMETTEUR (à confirmer)"
    return "BRUIT (classé)"


def summarize(rows: list[dict], label: str) -> list[str]:
    lines = [f"### {label}", "",
             "| événement | horizon | N | winrate | médiane bps | verdict |",
             "|---|---|---|---|---|---|"]
    for kind in DIRECTION:
        for hlabel in HORIZONS_H:
            vals = [r[hlabel] for r in rows if r["kind"] == kind and r[hlabel] is not None]
            n = len(vals)
            if n == 0:
                continue
            wins = sum(1 for v in vals if v > 0)
            wr = wins / n * 100.0
            med = sorted(vals)[n // 2]
            lines.append(
                f"| {kind} | {hlabel} | {n} | {wr:.1f} % | {med:+.1f} | {verdict_of(n, wr)} |"
            )
    lines.append("")
    return lines


def run_symbol(symbol: str, bars_count: int) -> tuple[str, list[str]] | None:
    try:
        bars = bars_from_klines(fetch_klines_paged(symbol, "1h", bars_count))
    except Exception as exc:  # noqa: BLE001
        return symbol, [f"### {symbol}", "", f"fetch impossible : {exc}", ""]
    if len(bars) < MIN_BARS:
        return symbol, [f"### {symbol}", "", f"historique insuffisant ({len(bars)} bougies)", ""]
    events = detect(bars)
    rows = forward_returns(bars, events)
    split = int(len(bars) * TRAIN_FRAC)
    train = [r for r in rows if r["i"] < split]
    val = [r for r in rows if r["i"] >= split]
    lines = [f"### {symbol} — {len(bars)} bougies 1h, {len(rows)} événements",
             "",
             f"train = {len(train)} événements (70 % anciens) · val = {len(val)} (30 % récents).",
             f"Coûts : {COST_BPS:g} bps aller-retour. Slippage non inclus.",
             ""]
    lines += summarize(train, "Train (70 %)")
    lines += summarize(val, "Val (30 % récents)")
    return symbol, lines


def main() -> int:
    p = argparse.ArgumentParser(description="Backtest absorption/sweep sur perps Aster")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--bars", type=int, default=3000)
    p.add_argument("--json", action="store_true", help="sortie JSON brute (événements)")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    all_rows: list[dict] = []
    report_parts = [
        "# Backtest Absorption & Sweep — perps Aster",
        "",
        f"Généré : {time.strftime('%d/%m/%Y %H:%M UTC', time.gmtime())} · règles EXACTES de "
        "l'indicateur (delta ≥ 2× baseline, corps ≤ 40 %, sweep ≥ 0.15 ATR + reclaim).",
        "",
        "**Règle pré-enregistrée** : N ≥ 10 ET winrate ≥ 55 % = prometteur ; "
        "N ≥ 10 et < 55 % = bruit classé ; N < 10 = insuffisant. Split 70/30. "
        f"Coûts {COST_BPS:g} bps aller-retour, slippage non inclus.",
        "",
        "**Avertissement multiplicité** : ce rapport teste ~12 combinaisons par "
        "symbole ; à 5 % de hasard, 1 surviving sur 20 est ATTENDU sans edge réel.",
        "",
    ]
    for sym in symbols:
        res = run_symbol(sym, args.bars)
        if res is None:
            continue
        _, lines = res
        report_parts += lines
        print(f"[bt] {sym}: {lines[0].split('—')[-1].strip()}")
        try:
            bars = None  # noqa: F841 — rows déjà agrégées dans le rapport
        except Exception:
            pass

    out = ROOT / "reports" / f"absorption-backtest-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.md"
    out.write_text("\n".join(report_parts) + "\n", encoding="utf-8")
    print(f"[rapport] {out}")
    if args.json:
        print(json.dumps(all_rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
