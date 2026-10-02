#!/usr/bin/env python
"""Le calculateur du PRIX DE LIQUIDATION EXACT — formule réelle Aster.

Le prix de liquidation n'est PAS une approximation : c'est une formule
fermée avec les paramètres réels du symbole (exchangeInfo → liq_params) :

  LONG  : LiqPrice = Entrée × (1 − 100/levier + maintMarginPercent/100)
  SHORT : LiqPrice = Entrée × (1 + 100/levier − maintMarginPercent/100)

Exemple PONSUSDT (maint 16,66 %) à 3x : Liq = Entrée × (1 − 0,3333 + 0,1666)
= Entrée × 0,8333 → la liquidation frappe à -16,67 % — exact, pas approximatif.

  .venv/bin/python scripts/liq_price.py PONSUSDT 0.707 long 3
  .venv/bin/python scripts/liq_price.py --demo    # les exemples des vedettes
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KDB = ROOT / "data" / "warehouse" / "klines.db"


def liq_price(entry: float, leverage: float, mm_pct: float, side: str) -> float:
    """Le prix de liquidation exact. mm_pct = maintMarginPercent (ex 16.66)."""
    mm = mm_pct / 100
    if side == "long":
        return entry * (1 - 1 / leverage + mm)
    return entry * (1 + 1 / leverage - mm)


def liq_move_pct(leverage: float, mm_pct: float) -> float:
    """Le mouvement adverse qui liquide, en % (la même formule vue côté mouvement)."""
    return 100 / leverage - mm_pct


def main() -> int:
    if len(sys.argv) >= 5:
        symbol, entry, side, lev = (sys.argv[1], float(sys.argv[2]),
                                    sys.argv[3].lower(), float(sys.argv[4]))
        con = sqlite3.connect(KDB, timeout=60)
        row = con.execute("SELECT maint_margin_pct, liq_fee, market_take_bound, "
                          "max_leverage FROM liq_params WHERE symbol=?",
                          (symbol,)).fetchone()
        con.close()
        if not row:
            print(f"symbole inconnu: {symbol}")
            return 1
        mm, fee, mtb, maxlev = row
        if lev > maxlev:
            print(f"⚠️ levier {lev}x > max autorisé {maxlev}x pour {symbol}")
            return 1
        lp = liq_price(entry, lev, mm, side)
        move = liq_move_pct(lev, mm)
        print(f"{symbol} {side.upper()} {lev}x @ {entry} :")
        print(f"  prix de liquidation EXACT : {lp:.6g} ({move:+.2f} % adverse)")
        print(f"  frais de liquidation si touché : {fee*100:.1f} % (en plus de la marge perdue)")
        print(f"  borne d'ordre marché : ±{mtb*100:.0f} % du mark par ordre")
        return 0

    # --demo : les positions vedettes du projet
    print("=== Les prix de liquidation des positions types (formule exacte) ===")
    cases = [
        ("PONSUSDT", 0.70695, "long", 3, "l'onde PONS (l'entrée des baleines)"),
        ("PONSUSDT", 0.70695, "short", 3, "le failed_ATH short"),
        ("BTCUSDT", 112000, "short", 20, "le 20x sur BTC (maint 2,5 %)"),
    ]
    con = sqlite3.connect(KDB, timeout=60)
    for sym, entry, side, lev, note in cases:
        row = con.execute("SELECT maint_margin_pct, liq_fee, max_leverage FROM "
                          "liq_params WHERE symbol=?", (sym,)).fetchone()
        mm, fee, maxlev = row
        lp = liq_price(entry, lev, mm, side)
        move = liq_move_pct(lev, mm)
        print(f"{sym} {side.upper()} {lev}x @ {entry} (maint {mm:.2f} %) : "
              f"liq {lp:.6g} ({move:+.2f} % adverse) — {note}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
