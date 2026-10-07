#!/usr/bin/env python
"""deep_fast — la profonde-rapide (CANDIDAT n°1 Aster, promotion 29/09).

Trigger (le scan des paramètres du cascade, docs/20 — pattern vectorisé des
études cascade) : 2 bougies 1h r1 < 0 (toutes deux négatives), accélération
ra > ra.shift(1), profondeur cumulée -(r1 + r1.shift(1)) >= 3.0 %.
SHORT, hold 24h, lev 7,5x, base 10 % — la promotion au paper tracking de la
machine (le forward décide de la promotion v5).

Le générateur scanne les DERNIÈRES bougies 1h (fenêtre 48 h = WINDOW_H du
paper forward), applique :
  - la fraîcheur : < 6 h depuis la CLÔTURE de la bougie signal ;
  - la non-recouvrance 24 h (le backtest du scan est non-recouvrant) ;
  - l'idempotence : les (sym, signal_ts) déjà dans paper_trades
    (signal='machine_deep_fast') ne sont jamais ré-émis.
Sortie main : JSON stdout {sym, signal_ts (ms), entry_price (close de la
bougie du signal), direction=-1}. Import : collect_deep_fast() — lisible
seulement (SELECT), aucun écrit, busy_timeout (doctrine sqlite).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
DEPTH_PCT = 3.0          # -(r1 + r1.shift(1)) >= 3.0 %
NON_OVERLAP_H = 24       # le scan du cascade : non-recouvrant 24 h
FRESH_H = 6              # signaux < 6 h (depuis la clôture de la bougie)
WINDOW_H = 48            # la fenêtre de détection (= WINDOW_H paper forward)
HOLD_H = 24
DIRECTION = -1
SIGNAL_NAME = "machine_deep_fast"


def collect_deep_fast(con: sqlite3.Connection, fresh_h: int = FRESH_H,
                      window_h: int = WINDOW_H) -> list[dict]:
    """Les signaux deep_fast frais, jamais ré-émis.

    Convention machine (le bloc machine du paper forward divise ts_ms par
    10**6) : le champ "ts_ms" retenu ici est en NANOSECONDES. La sortie
    JSON du main, elle, expose signal_ts en ms (le contrat de la mission).
    """
    now_ms = int(time.time() * 1000)
    win_ms = window_h * 3600 * 1000
    fresh_min_ts = now_ms - (fresh_h + 1) * 3600 * 1000  # clôture < fresh_h
    overlap_ms = NON_OVERLAP_H * 3600 * 1000
    emitted = {(s, int(t)) for s, t in con.execute(
        "SELECT symbol, signal_ts FROM paper_trades WHERE signal=?",
        (SIGNAL_NAME,)).fetchall()}
    out: list[dict] = []
    for sym in MAJORS:
        df = load_df(con, sym)
        if df is None:
            continue
        r1 = df["close"].pct_change() * 100
        ra = r1.abs()
        mask = ((r1 < 0) & (r1.shift(1) < 0) & (ra > ra.shift(1))
                & (-(r1 + r1.shift(1)) >= DEPTH_PCT)).fillna(False)
        idx_ns = df.index.astype("datetime64[ns]").asi8
        last_emit = max([t for (s, t) in emitted if s == sym],
                        default=-(1 << 62))
        for t in np.where(mask.values)[0]:
            ts_ms = int(idx_ns[t]) // 10**6       # open_time de la bougie
            if ts_ms < now_ms - win_ms:
                continue                          # hors fenêtre 48 h
            if ts_ms < fresh_min_ts:
                continue                          # pas frais (< 6 h clôture)
            if (sym, ts_ms + 3_600_000) in emitted:
                # PR-171 (P2) : paper_forward stocke signal_ts = CLOSE(t)
                # (open + 1h) — l'ancien comparait l'open : l'idempotence
                # ne matchait JAMAIS (écart exact 3 600 000 ms) et la
                # non-ré-émission ne tenait qu'à l'accident du check 24 h
                last_emit = max(last_emit, ts_ms)
                continue                          # déjà émis : jamais ré-émis
            if ts_ms - last_emit < overlap_ms:
                continue                          # non-recouvrant 24 h
            last_emit = ts_ms
            # FIX audit v3 (C14) : l'entrée = la CLOSE de la bougie du signal
            # (convention documentée) — le timestamp doit donc être l'INSTANT
            # de cette close, pas l'open de la même bougie (couple inexécutable
            # open(t) + close(t) avant).
            out.append({"sym": sym, "ts_ms": int(idx_ns[t]) + 3_600 * 10**9,
                        "entry": float(df["close"].iloc[t]),
                        "direction": DIRECTION, "hold_h": HOLD_H,
                        "depth_pct": round(float(
                            -(r1.iloc[t] + r1.iloc[t - 1])), 2)})
    return out


def main() -> int:
    con = sqlite3.connect(KDB, timeout=30)   # busy_timeout 30 s, SELECT seul
    try:
        sigs = collect_deep_fast(con)
    finally:
        con.close()
    now_ms = int(time.time() * 1000)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signal": SIGNAL_NAME, "trigger": "2 bougies r1<0, ra>ra.shift(1), "
        f"depth>= {DEPTH_PCT} %", "window_h": WINDOW_H, "fresh_h": FRESH_H,
        "n_signals": len(sigs),
        "signals": [{"sym": s["sym"], "signal_ts": s["ts_ms"] // 10**6,
                     "entry_price": s["entry"],
                     "direction": s["direction"]} for s in sigs],
    }
    print(json.dumps(payload, indent=2))
    if sigs:
        ages = [(now_ms - s["ts_ms"] // 10**6) / 3600000 for s in sigs]
        print(f"[deep_fast] {len(sigs)} signal(aux) frais "
              f"(age {min(ages):.1f}-{max(ages):.1f} h) -> "
              f"ledger au prochain passage nocturne", file=sys.stderr)
    else:
        print("[deep_fast] 0 signal frais sur la fenêtre", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
