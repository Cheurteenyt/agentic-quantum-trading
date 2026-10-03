#!/usr/bin/env python3
"""Le moniteur de régime de l'edge (28/09) — le recount roulant 90 j
du gated cascade majors, l'état de l'adaptateur (seuil plat 0,30 %,
×0,75 sous le seuil, retour ×1 après 30 j au-dessus).
Le recount trimestriel = reports/decay-curve-2026-09-28.md."""
import sys, sqlite3, collections, datetime
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.anti_liq import add_rolling_scores, collect_featured
from scripts.portfolio_sim import MAJORS, btc_regime_series
from scripts.stacked_portfolio import funding_hourly_all

SEUIL = 0.30          # % de marge — l'alternative testée ; OFFICIEL pré-enregistré = p25 +0.722 (regime-adapter-2026-09-28.md §Pré-enregistrements)
MIN_N = 10            # min_n du pré-enregistrement — sous 10 trades, pas de verdict
RAPPORT = Path(__file__).resolve().parents[1] / "reports" / "edge-regime-monitor.log"


def main() -> int:
    con = sqlite3.connect(str(Path(__file__).resolve().parents[1] /
                              "data" / "warehouse" / "klines.db"), timeout=60)
    fh = funding_hourly_all()
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"; e["lev"] = 10
        e["hold_h"] = 24; e["fee_rt_bps"] = 0.09
    add_rolling_scores(events)
    q66 = float(np.nanquantile([e.get("al_score", float("nan"))
                                for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    # l'espérance roulante 90 j : les rets des 90 derniers jours glissants
    now_s = datetime.datetime.now(datetime.UTC).timestamp()
    win = [e for e in gated
           if now_s - e["ts_ms"] / 1e9 <= 90 * 86400
           and e.get("price_ret_short") is not None]
    roll = sum(e["price_ret_short"] for e in win) / len(win) if win else float("nan")
    if len(win) < MIN_N or roll != roll:  # fenêtre vide/n<min_n = pas de verdict
        etat = f"INDÉTERMINÉ (n={len(win)} < min_n {MIN_N}) — régime inchangé"
    elif roll < SEUIL:
        etat = "DÉRISKÉ ×0,75 (roulante < 0,30 %)"
    else:
        etat = "PLEIN RÉGIME (roulante ≥ 0,30 %)"
    line = (f"{datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')} | "
            f"roulante 90 j = {roll:+.2f} % sur {len(win)} trades | {etat}\n")
    print(line, end="")
    with open(RAPPORT, "a") as f:
        f.write(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
