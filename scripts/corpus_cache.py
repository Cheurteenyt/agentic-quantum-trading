#!/usr/bin/env python3
"""LE CACHE DE CORPUS (29/09) — le corpus gated cascade construit UNE fois
(les events + les features + le CVD pré-attaché), sérialisé en pickle.
Toute étude charge le cache en secondes au lieu de reconstruire en minutes.
Usage : --build (reconstruit) | le import : from scripts.corpus_cache import load_corpus"""
import sys, pickle, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CACHE = ROOT / "data" / "cache" / "cascade_corpus.pkl"


def build_corpus():
    """Le corpus gated + le CVD pré-attaché (les ratios taker par event)."""
    import sqlite3
    import numpy as np
    from scripts.anti_liq import add_rolling_scores, collect_featured
    from scripts.portfolio_sim import MAJORS, btc_regime_series

    con = sqlite3.connect(str(ROOT / "data" / "warehouse" / "klines.db"), timeout=30)
    fh_map = {}
    for s, r in con.execute("SELECT symbol, rate FROM funding_history"):
        try: fh_map.setdefault(s, []).append(float(r))
        except (TypeError, ValueError): continue
    fh_avg = {s: sum(v)/len(v)*100/8 for s, v in fh_map.items() if v}

    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    add_rolling_scores(events)   # EN PLACE — la fonction retourne None (piège d'assignation)
    q66 = float(np.nanquantile([e.get("al_score", float("nan"))
                                for e in events[:int(len(events)*0.7)]], 2/3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan"))) and e["al_score"] >= q66)]
    # le CVD pré-attaché : le buy_ratio 1h des 4 bougies précédant chaque event
    cvd = {}
    for sym in {e["sym"] for e in gated}:
        rows = con.execute("""SELECT open_time, taker_buy_volume, volume FROM klines
                              WHERE symbol=? AND interval='1h' AND taker_buy_volume IS NOT NULL
                              ORDER BY open_time""", (sym,)).fetchall()
        if rows:
            cvd[sym] = (np.array([r[0] for r in rows]),
                        np.array([ (r[1]/r[2]) if r[2] else np.nan for r in rows]))
    con.close()
    kept, n_no_cvd = [], 0
    for e in gated:
        arr = cvd.get(e["sym"])
        if arr is None: n_no_cvd += 1; continue
        t = e["ts_ms"]/1e6
        i = int(np.searchsorted(arr[0], t))
        window = arr[1][max(0, i-4):i]
        e["buy_ratio"] = float(np.nanmean(window)) if len(window) else np.nan
        kept.append(e)
    return kept, n_no_cvd


def load_corpus(rebuild=False):
    """Le corpus caché — reconstruit si absent ou --build."""
    if CACHE.exists() and not rebuild:
        with open(CACHE, "rb") as f:
            evs = pickle.load(f)
        return evs
    evs, n_no = build_corpus()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(evs, f)
    return evs


if __name__ == "__main__":
    if "--build" in sys.argv or not CACHE.exists():
        t0 = time.time()
        evs, n_no = build_corpus()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE, "wb") as f:
            pickle.dump(evs, f)
        print(f"[cache] construit : {len(evs)} events gated (CVD manquant : {n_no}) "
              f"en {time.time()-t0:.0f}s → {CACHE.name}")
    else:
        t0 = time.time()
        evs = load_corpus()
        print(f"[cache] chargé : {len(evs)} events en {(time.time()-t0)*1000:.0f} ms")
