#!/usr/bin/env python3
"""LE PREFLIGHT — Research OS PR 3 (brief V3 §42-47).

La chaîne d'exécution d'une confirmation : PLANNED → PREFLIGHT → READY →
RESERVED → RUNNING → SEALED → VERIFIED → VERDICT. Seul READY peut réserver
un slot — et PREFLIGHT_FAILED consomme ZÉRO slot scientifique.

La leçon W42 gravée ici : IMPORT OK ≠ PIPELINE OK — une fonction couplée à
la DB peut casser malgré des imports verts (la colonne open_time). Donc le
preflight vérifie le SCHÉMA RÉEL, la couverture RÉELLE, et exécute un
SMOKE TEST sur les vraies données avant que le moindre slot soit engagé.

Checks :
  1. la DB existe et est lisible ;
  2. les tables requises existent (klines, funding_history) ;
  3. les colonnes requises de klines existent (open_time, open, high, low,
     close, symbol, interval) — le crash open_time ne peut plus se reproduire ;
  4. couverture par symbole : des barres dans la fenêtre du scope ;
  5. monotonicité des timestamps (open_time strictement croissant, spot check) ;
  6. couverture funding par symbole ;
  7. SMOKE RÉEL : _attach_marks sur un event ancré sur une vraie kline.

Usage :
  python scripts/preflight.py --snapshot-id S1 --train-start 0 --train-end 1e12 \\
      --validation-start 1e12 --validation-end 2e12 --symbols BTCUSDT,ETHUSDT

Exit 0 = PREFLIGHT_OK (READY) · 1 = PREFLIGHT_FAILED (0 slot consommé).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research_os import DataScope  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
KLINES_COLS = {"symbol", "interval", "open_time", "open", "high", "low", "close"}


def preflight(scope: DataScope, symbols: list[str],
              db_path: Path = KDB, con: sqlite3.Connection | None = None) -> dict:
    """Exécute les checks de santé des données. Ne juge pas, mesure —
    le verdict est PREFLIGHT_OK ou PREFLIGHT_FAILED avec les motifs."""
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    own = con is None
    try:
        con = con or sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.execute("SELECT 1").fetchone()   # la DB doit exister et être lisible
    except sqlite3.Error as exc:
        return {"verdict": "PREFLIGHT_FAILED",
                "checks": [{"check": "DB lisible", "ok": False, "detail": str(exc)}]}
    try:
        # 1-2. les tables et colonnes requises (la leçon open_time)
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        check("tables requises", {"klines", "funding_history"} <= tables,
              f"manquantes: {sorted({'klines', 'funding_history'} - tables)}")
        kcols = {r[1] for r in con.execute("PRAGMA table_info(klines)")}
        missing = KLINES_COLS - kcols
        check("colonnes klines", not missing,
              f"manquantes: {sorted(missing)}" if missing else "OK")
        if missing:
            return {"verdict": "PREFLIGHT_FAILED", "checks": checks}

        lo = scope.train_start_ms
        hi = scope.validation_end_ms
        # 3-5. par symbole : couverture, monotonicité, funding
        for sym in symbols:
            rows = con.execute(
                "SELECT open_time FROM klines WHERE symbol=? AND interval='1h' "
                "AND open_time BETWEEN ? AND ? ORDER BY open_time",
                (sym, lo, hi)).fetchall()
            check(f"couverture klines {sym}", len(rows) > 0,
                  f"{len(rows)} barres dans la fenêtre")
            if len(rows) >= 2:
                ts = [r[0] for r in rows[:2000]]
                check(f"monotonicité {sym}", all(b > a for a, b in zip(ts, ts[1:])),
                      f"{len(ts)} barres spot-check")
                # FIX v8 (rapport GLM 5.3 №19) : les TROUS horaires — la
                # monotonicité seule laisse passer 10:00, 11:00, 13:00. Le
                # kernel masque désormais les labels à travers un gap
                # (contiguïté exigée) ; ici on les rend VISIBLES.
                gaps = sum(1 for a, b in zip(ts, ts[1:]) if b - a != 3_600_000)
                max_gap = max((b - a for a, b in zip(ts, ts[1:])),
                              default=0) // 3_600_000
                check(f"trous horaires {sym}", gaps == 0,
                      f"{gaps} trou(s)/doublon(s) · écart max {max_gap} h "
                      "— les labels à travers un trou sont masqués (gapless)")
            frows = con.execute(
                "SELECT COUNT(*) FROM funding_history WHERE symbol=? "
                "AND funding_time BETWEEN ? AND ?",
                (sym, lo, hi)).fetchone()[0]
            check(f"couverture funding {sym}", frows > 0, f"{frows} prints")

        # 6. SMOKE RÉEL : le crash W42 (marks sur une vraie kline) ne peut
        #    plus passer inaperçu avant un run.
        from scripts.qubo_sizing import _attach_marks
        probe_sym = symbols[0] if symbols else "BTCUSDT"
        row = con.execute(
            "SELECT open_time, open FROM klines WHERE symbol=? AND interval='1h' "
            "AND open_time BETWEEN ? AND ? ORDER BY open_time LIMIT 1",
            (probe_sym, lo, hi)).fetchone()
        if row is None:
            check("smoke marks", False, f"aucune kline pour {probe_sym}")
        else:
            ev = {"sym": probe_sym, "strategy": "survivor_long",
                  "ts_ms": int(row[0]) * 10**6, "hold_h": 2,
                  "entry": float(row[1])}
            try:
                _attach_marks(con, [ev])
                check("smoke marks", len(ev.get("marks", [])) > 0,
                      f"{len(ev.get('marks', []))} marks générés")
            except Exception as exc:  # le crash W42 exact
                check("smoke marks", False, f"EXCEPTION: {exc}")
    finally:
        if own:
            con.close()

    ok = all(c["ok"] for c in checks)
    return {"verdict": "PREFLIGHT_OK" if ok else "PREFLIGHT_FAILED",
            "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--snapshot-id", required=True)
    ap.add_argument("--train-start", type=float, required=True, help="ms")
    ap.add_argument("--train-end", type=float, required=True, help="ms")
    ap.add_argument("--validation-start", type=float, required=True, help="ms")
    ap.add_argument("--validation-end", type=float, required=True, help="ms")
    ap.add_argument("--symbols", default="BTCUSDT", help="séparés par des virgules")
    ap.add_argument("--db", default=str(KDB))
    a = ap.parse_args()
    scope = DataScope(a.snapshot_id, int(a.train_start), int(a.train_end),
                      int(a.validation_start), int(a.validation_end))
    res = preflight(scope, [s.strip().upper() for s in a.symbols.split(",")],
                    db_path=Path(a.db))
    for c in res["checks"]:
        print(f"  [{'OK ' if c['ok'] else 'ÉCHEC'}] {c['check']}"
              + (f" — {c['detail']}" if c["detail"] else ""))
    msg = ("READY : le slot peut être réservé" if res["verdict"] == "PREFLIGHT_OK"
           else "PREFLIGHT_FAILED : 0 slot consommé, corriger avant tout run")
    print(f"\nVERDICT : {res['verdict']} — {msg}")
    return 0 if res["verdict"] == "PREFLIGHT_OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
