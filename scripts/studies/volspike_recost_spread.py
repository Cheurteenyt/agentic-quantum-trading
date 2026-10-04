# volspike_recost_spread.py — LE RE-COST du flux vol_spike_6h au spread réel par symbole.
# Pré-enregistré dans research/hypotheses/execution-slippage-protocol.md (mutation de coût).
#
# CORRECTION DE RÉFÉRENTIEL (04/10, avant le run) : le RT assumé de la machine = TAKER_RT 28 bps
# ((4 frais + 10 slippage) × 2) — PAS les 8 bps du backtest premium-fade. Le plancher de spread
# mesuré (execution_depth_floor.py, n=301) s'additionne aux frais : RT réel ≈ spread_full + 8.
# Le test : le flux FROZEN (seuils p5 intouchés) re-costé par symbole tient-il ses chiffres ?
#
# RÈGLE pré-enregistrée : espérance nette ≤ 0 au coût réel → flux invalidé EN TAKER.
# Le mode maker (spread récupéré si fill) est la QUESTION SUIVANTE, pas une réparation.

import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]   # scripts/studies/ → racine (le piège e906ac2)
sys.path.insert(0, str(ROOT))

from scripts.p5_frequency_test import run_flat, stats_block  # noqa: E402
from scripts.volspike_meme_test import collect_vol_spike_meme  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, TAKER_RT, funding_hourly_all, run_stack)

KDB = ROOT / "data" / "warehouse" / "klines.db"
SIZE = 0.05
FEE_LEG = 4.0          # frais taker bps/jambe (TAKER_RT = (4+10)*2 ; ici slippage = spread RÉEL)

# Les planchers de spread MESURÉS (execution_depth_floor.py, médiane par symbole, 04/10).
SPREAD_MEASURED = {
    "BTCUSDT": 0.0, "ETHUSDT": 0.0, "ASTERUSDT": 2.0, "TRUMPUSDT": 10.0,
    "PONSUSDT": 8.0, "TURBOUSDT": 13.0, "WIFUSDT": 12.0, "PNUTUSDT": 16.0,
    "FARTCOINUSDT": 16.0, "MOODENGUSDT": 18.0, "DOGSUSDT": 22.0,
    "BOMEUSDT": 24.0, "NEIROUSDT": 24.0, "CATEUSDT": 152.0, "MEMEUSDT": 200.0,
}
FALLBACK_SPREAD = 16.0   # la médiane de la classe meme MESURÉE (hors les 2 extrêmes)


def real_rt(sym: str) -> float:
    return SPREAD_MEASURED.get(sym, FALLBACK_SPREAD) + 2 * FEE_LEG


def stats(res) -> dict:
    pnls = [t["pnl"] for t in res["trades"]]
    margins = [t["margin"] for t in res["trades"]]
    mrows = monthly_rows(res["trades"], CAPITAL)
    dd = 0.0
    peak = 0.0
    cum = 0.0
    for r in mrows:
        cum += r["pnl"]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return {"n": res["n"], "wr": res["n_wins"] / max(res["n"], 1) * 100,
            "exp": float(np.mean(pnls)) if pnls else 0.0,
            "mae_max": 0.0,  # le MAE vit sur l event, pas le trade — les liq du run_stack font foi
            "liq": res["n_liq"],
            "roi_an": (res["balance"] / CAPITAL - 1) * 100 * 12 / max(len(mrows), 1),
            "dd": dd, "months": len(mrows),
            "neg": sum(1 for r in mrows if r["pnl"] <= 0)}


def main():
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=60)
    fh = funding_hourly_all()
    ev_a = collect_vol_spike_meme(con)   # le flux du REGISTRE (variante A native, frozen)
    con.close()
    print(f"events vol_spike_meme (frozen, variante A) : {len(ev_a):,}")
    months = 12  # la convention stats_block de l'original

    base = stats_block(run_flat([dict(e) for e in ev_a], fh, TAKER_RT,
                                "vol_spike_meme"), months)
    evs2 = [dict(e) for e in ev_a]
    for e in evs2:
        e["fee_rt_bps"] = real_rt(e["sym"])
    real = stats_block(run_stack(evs2, CAPITAL, lambda e, st=None: SIZE, fh), months)

    print("\n== FLUX vol_spike_meme — baseline 28 bps flat vs coût RÉEL par symbole ==")
    print(f"{'':22s}{'baseline':>12s}{'réel':>12s}")
    for k, lbl in [("n", "n trades"), ("wr", "WR %"), ("exp", "esp $/trade"),
                   ("roi", "ROI % (total)"), ("mae_max", "MAE max %")]:
        print(f"{lbl:22s}{base[k]:>12.3f}{real[k]:>12.3f}")
    print(f"liq                    {base['res']['n_liq']:>6d}{real['res']['n_liq']:>8d}")
    print(f"balance finale $       {base['res']['balance']:>8.2f}{real['res']['balance']:>8.2f}")

    pricey = [e for e in ev_a if real_rt(e["sym"]) > TAKER_RT]
    share = len(pricey) / max(len(ev_a), 1) * 100
    from collections import Counter
    cc = Counter(e["sym"] for e in pricey)
    print(f"\nevents au-delà de l'hypothèse 28 bps : {len(pricey):,} ({share:.1f} %) {dict(cc)}")
    print(f"fallback spread non-mesuré : {FALLBACK_SPREAD:.0f} bps (médiane meme mesurée) → "
          f"RT réel médian non-mesuré = {FALLBACK_SPREAD + 2*FEE_LEG:.0f} bps vs 28 assumés")

    if real["exp"] <= 0:
        verdict = "INVALIDÉ EN TAKER (espérance ≤ 0 au coût réel) — la question maker devient la suite"
    else:
        delta = (real["exp"] - base["exp"]) / max(abs(base["exp"]), 1e-9) * 100
        verdict = (f"TIENT au coût réel (esp {base['exp']:+.4f} → {real['exp']:+.4f} $/trade, "
                   f"Δ {delta:+.1f} %) — l'hypothèse 28 bps couvrait le spread médian mesuré")
    print(f"\nVERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
