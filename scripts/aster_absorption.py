#!/usr/bin/env python
"""Signaux order-flow (absorption / sweep) sur données ASTER natives.

MMT/M5 ne couvre pas Aster (voir docs/17-mmt-m5.md). Ce script applique les
MÊMES règles que l'indicateur MMT « Absorption & Sweep » aux klines Aster,
qui exposent le volume taker buy par bougie — donc le delta acheteur/vendeur
sur les VRAIS prix du lieu d'exécution.

Règles (identiques à l'indicateur MMT, rev 5) :
- absorption : |delta| >= thr_mult x moyenne mobile des |delta| (fenêtre len),
  corps <= max_body_frac du range, clôture à contre-sens du delta
  (delta<0 & close>=open => acheteurs absorbent ; delta>0 & close<=open => vendeurs)
- sweep : perforation du plus-bas/plus-haut des sweep_len bougies précédentes
  d'au moins sweep_atr_frac x ATR(period), reclaim en clôture (close dans les
  40 % opposés du range)

Usage :
  .venv/bin/python scripts/aster_absorption.py --symbol BTCUSDT --interval 30m
  .venv/bin/python scripts/aster_absorption.py --symbol BTCUSDT,ETHUSDT,ASTERUSDT --last 15
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "klines.db"

ASTERNDEX_BASE = "https://fapi.asterdex.com/fapi/v1/klines"

FLOW_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS flow_events (
    symbol      TEXT    NOT NULL,
    interval    TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    bar_time    INTEGER NOT NULL,
    close       REAL    NOT NULL,
    delta       REAL    NOT NULL,
    baseline    REAL    NOT NULL,
    depth_atr   REAL    NOT NULL,
    params      TEXT    NOT NULL,
    captured_at REAL    NOT NULL,
    PRIMARY KEY (symbol, interval, kind, bar_time, params)
);
"""


def param_signature(params: dict) -> str:
    """Empreinte compacte des paramètres : changer un seuil crée une nouvelle
    famille d'événements au lieu de corrompre l'accumulation en cours."""
    return (
        f"l{params['len_baseline']}_t{params['thr_mult']}"
        f"_b{params['max_body_frac']}_s{params['sweep_len']}"
        f"_a{params['sweep_atr_frac']}"
    )


def init_flow_db(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=60)
    con.execute(FLOW_EVENTS_DDL)
    con.commit()
    return con


def record_events(rows: list[dict], db_path: Path | str = DB_PATH) -> int:
    """Insertion idempotente (PK composite) ; retourne le nb de nouvelles lignes."""
    if not rows:
        return 0
    con = init_flow_db(db_path)
    try:
        cur = con.executemany(
            "INSERT OR IGNORE INTO flow_events "
            "(symbol, interval, kind, bar_time, close, delta, baseline, depth_atr, params, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r["symbol"],
                    r["interval"],
                    r["kind"],
                    r["bar_time"],
                    r["close"],
                    r["delta"],
                    r["baseline_abs_delta"],
                    r["depth_atr"],
                    r["params"],
                    time.time(),
                )
                for r in rows
            ],
        )
        con.commit()
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    finally:
        con.close()


def fetch_klines(symbol: str, interval: str, limit: int = 400) -> list:
    url = f"{ASTERNDEX_BASE}?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "trading-agent/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def bars_from_klines(klines: list) -> list[dict]:
    """klines Binance-compatible : [openTime,o,h,l,c,vol,closeTime,quoteVol,n,trades,takerBuyBase,takerBuyQuote,ignore]"""
    bars = []
    for k in klines:
        o, h, low, c = (float(k[1]), float(k[2]), float(k[3]), float(k[4]))
        volume = float(k[5])
        taker_buy = float(k[9])
        bars.append(
            {
                "t": int(k[0]) // 1000,
                "o": o,
                "h": h,
                "l": low,
                "c": c,
                "buy": taker_buy,
                "sell": volume - taker_buy,
            }
        )
    return bars


def atr(bars: list[dict], i: int, period: int = 14) -> float | None:
    if i < period:
        return None
    trs = []
    for k in range(i - period + 1, i + 1):
        hh, ll = bars[k]["h"], bars[k]["l"]
        pc = bars[k - 1]["c"] if k > 0 else bars[k]["o"]
        trs.append(max(hh - ll, abs(hh - pc), abs(ll - pc)))
    return sum(trs) / len(trs)


def detect(
    bars: list[dict],
    len_baseline: int = 50,
    thr_mult: float = 2.0,
    max_body_frac: float = 0.4,
    sweep_len: int = 20,
    sweep_atr_frac: float = 0.15,
    atr_period: int = 14,
) -> list[dict]:
    events: list[dict] = []
    abs_deltas: list[float] = []
    for i, b in enumerate(bars):
        rng = b["h"] - b["l"]
        delta = b["buy"] - b["sell"]
        abs_deltas.append(abs(delta))
        if rng <= 0:
            continue
        # absorption (baseline = moyenne des |delta| sur len_baseline bougies, courante incluse)
        if len(abs_deltas) >= len_baseline:
            base = sum(abs_deltas[-len_baseline:]) / len_baseline
            body = abs(b["c"] - b["o"])
            if base > 0 and abs(delta) >= thr_mult * base:
                if delta < 0 and body <= max_body_frac * rng and b["c"] >= b["o"]:
                    events.append({"i": i, "kind": "absorption_buy", "delta": delta, "baseline": base})
                elif delta > 0 and body <= max_body_frac * rng and b["c"] <= b["o"]:
                    events.append({"i": i, "kind": "absorption_sell", "delta": delta, "baseline": base})
        # sweep (fenêtre = sweep_len bougies PRÉCÉDENTES, comme le rolling MMT lu avant push)
        if i >= sweep_len:
            a = atr(bars, i, atr_period)
            if not a or a <= 0:
                continue
            prev_low = min(x["l"] for x in bars[i - sweep_len : i])
            prev_high = max(x["h"] for x in bars[i - sweep_len : i])
            close_pos = (b["c"] - b["l"]) / rng
            if prev_low - b["l"] >= sweep_atr_frac * a and b["c"] > prev_low and close_pos >= 0.6:
                events.append({"i": i, "kind": "sweep_low", "depth_atr": (prev_low - b["l"]) / a})
            if b["h"] - prev_high >= sweep_atr_frac * a and b["c"] < prev_high and (1.0 - close_pos) >= 0.6:
                events.append({"i": i, "kind": "sweep_high", "depth_atr": (b["h"] - prev_high) / a})
    return events


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M")


def run(symbol: str, interval: str, limit: int, last: int, params: dict) -> list[dict]:
    bars = bars_from_klines(fetch_klines(symbol, interval, limit))
    events = detect(bars, **params)
    if last >= 0:
        events = events[-last:]
    sig = param_signature(params)
    out = []
    for ev in events:
        b = bars[ev["i"]]
        out.append(
            {
                "symbol": symbol,
                "interval": interval,
                "kind": ev["kind"],
                "bar_time": b["t"],
                "time_utc": _fmt_ts(b["t"]),
                "close": b["c"],
                "delta": round(ev.get("delta", 0.0), 3),
                "baseline_abs_delta": round(ev.get("baseline", 0.0), 3),
                "depth_atr": round(ev.get("depth_atr", 0.0), 2),
                "params": sig,
            }
        )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Absorption & Sweep sur klines Aster natives")
    p.add_argument("--symbol", default="BTCUSDT", help="symboles séparés par des virgules")
    p.add_argument("--interval", default="30m")
    p.add_argument("--limit", type=int, default=400)
    p.add_argument("--last", type=int, default=12, help="garder les N derniers événements (-1 = tout)")
    p.add_argument("--len-baseline", type=int, default=50)
    p.add_argument("--thr-mult", type=float, default=2.0)
    p.add_argument("--max-body-frac", type=float, default=0.4)
    p.add_argument("--sweep-len", type=int, default=20)
    p.add_argument("--sweep-atr-frac", type=float, default=0.15)
    p.add_argument("--record", action="store_true",
                   help="insérer les événements de la fenêtre dans flow_events (klines.db) ; --last est ignoré")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    params = dict(
        len_baseline=args.len_baseline,
        thr_mult=args.thr_mult,
        max_body_frac=args.max_body_frac,
        sweep_len=args.sweep_len,
        sweep_atr_frac=args.sweep_atr_frac,
    )

    all_rows: list[dict] = []
    for sym in [s.strip().upper() for s in args.symbol.split(",") if s.strip()]:
        try:
            # --record accumule TOUTE la fenêtre (idempotent), pas juste les N derniers
            all_rows.extend(run(sym, args.interval, args.limit, -1 if args.record else args.last, params))
        except Exception as exc:  # noqa: BLE001 — un symbole en échec ne bloque pas les autres
            print(f"[WARN] {sym}: {exc}", file=sys.stderr)

    if args.record:
        inserted = record_events(all_rows, args.db)
        print(f"[record] {inserted} nouveaux événements -> {args.db} (fenêtre : {len(all_rows)})")

    if args.json:
        print(json.dumps(all_rows, indent=1))
        return 0

    if not all_rows:
        print("Aucun événement détecté.")
        return 0
    header = f"{'SYMBOLE':<12} {'HEURE UTC':<11} {'TYPE':<16} {'CLOSE':>12} {'DELTA':>12} {'BASE |D|':>12} {'PROF ATR':>8}"
    print(header)
    print("-" * len(header))
    for r in all_rows:
        print(
            f"{r['symbol']:<12} {r['time_utc']:<11} {r['kind']:<16} {r['close']:>12.4f} "
            f"{r['delta']:>12.3f} {r['baseline_abs_delta']:>12.3f} {r['depth_atr']:>8.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
