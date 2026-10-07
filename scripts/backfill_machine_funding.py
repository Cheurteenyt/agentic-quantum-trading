#!/usr/bin/env python3
"""PR-167 (P1 couche argent) — backfill ONE-SHOT du ledger machine.

Les 124 clôtures antérieures au 02/10 12:21 UTC ont tourné sur la
convention PRÉ-F3 : ret = prix − coûts − d×moyenne_full_sample×hold —
exactement le look-ahead que F3 a tué — et l'UPDATE n'écrivait pas
funding_pct (ledger inauditable : 124/124 NULL). Preuve bug-hunter : le
résidu ret−(prix−coûts) est constant PAR SYMBOLE = la moyenne full-sample.

Ce script réécrit funding_pct avec le funding RÉEL de la fenêtre
(funding_paid_pct : les taux signés de funding_history sur (entrée,
sortie]) et ret avec la recomposition canonique
prix×direction − COST_PCT + funding_appliqué. IDEMPOTENT : ne touche que
les lignes funding_pct IS NULL (les clôtures post-F3 sont déjà correctes).

    python scripts/backfill_machine_funding.py            # dry-run
    python scripts/backfill_machine_funding.py --apply    # écrit
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.paper_forward import (  # noqa: E402
    COST_PCT, KDB, funding_applied_pct, funding_paid_pct)


def main() -> int:
    apply = "--apply" in sys.argv
    con = sqlite3.connect(KDB, timeout=60)
    rows = con.execute(
        "SELECT rowid, signal, symbol, direction, entry_ts, exit_ts, "
        "entry_price, exit_price, ret_pct, funding_pct FROM paper_trades "
        "WHERE signal LIKE 'machine_%' AND status='closed' "
        "AND funding_pct IS NULL").fetchall()
    if not rows:
        print("rien à backfiller (0 ligne funding_pct IS NULL)")
        return 0
    tot_d = 0.0
    max_d = 0.0
    n = 0
    for (rid, sig, sym, d, t0, t1, pe, px, ret_old,
         _fp) in rows:
        fund_real = funding_paid_pct(con, sym, t0, t1)
        fund_applied = funding_applied_pct(d, fund_real)
        price_comp = (px - pe) / pe * 100.0 * d
        ret_new = price_comp - COST_PCT + fund_applied
        delta = ret_new - float(ret_old)
        tot_d += delta
        max_d = max(max_d, abs(delta))
        n += 1
        if apply:
            con.execute(
                "UPDATE paper_trades SET funding_pct=?, ret_pct=? "
                "WHERE rowid=?", (round(fund_applied, 4), round(ret_new, 4),
                                  rid))
        else:
            print(f"  [dry] {sig}/{sym} ret {ret_old:.3f} → {ret_new:.3f} "
                  f"(Δ {delta:+.3f}, fund {fund_applied:+.4f})")
    if apply:
        con.commit()
    con.close()
    mode = "APPLY" if apply else "DRY-RUN (--apply pour écrire)"
    print(f"{mode} : {n} lignes · Δret total {tot_d:+.3f} pts · "
          f"|Δ| max {max_d:.3f} pts · COST_PCT {COST_PCT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
