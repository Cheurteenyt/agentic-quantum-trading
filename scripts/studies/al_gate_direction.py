# al_gate_direction.py — l'A/B du SENS du gate AL (F-037, re-preuve du 07/10).
#
# La re-preuve (reports/al-gradient-reproof-2026-10-07.md) a montré que le
# score CORRIGÉ (PR-172) prédit le risque (liq monotone croissant) mais que
# le gate machine (>= q66) sélectionne le tercile le PLUS risqué. Cette
# étude fait juger le SENS par le wallet (le juge désigné) : trois
# variantes, tout le reste identique (sizing vol-inverse ×K, levier asservi
# MAE, créneaux run_stack, funding réel par fenêtre — désormais complet
# depuis le backfill PR-177).
#
# DISCOVERY : train/val observés séparément, JAMAIS promote sans confirmation.

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np

from scripts.anti_liq import add_rolling_scores, collect_featured
from scripts.portfolio_sim import HOLD_H, btc_regime_series
from scripts.stacked_portfolio import (
    CAPITAL, TAKER_RT, funding_hourly_all, run_stack)
from scripts.the_machine import MACHINE_K, levier_majors_safe

WARMUP = 30          # le socle du gate expanding (doctrine PR-167)


def expanding_gate(events: list[dict], side: str) -> list[dict]:
    """Garde les events au-dessus (hot) / en-dessous (cold) du quantile
    EXPANDING des scores passés ; pas de gate pendant le socle."""
    out, hist = [], []
    q = 2 / 3 if side == "hot" else 1 / 3
    for e in events:
        s = e.get("al_score", float("nan"))
        if len(hist) >= WARMUP:
            thr = float(np.nanquantile(hist, q))
            ok = (np.isfinite(s) and s >= thr) if side == "hot" \
                else (np.isfinite(s) and s <= thr)
            if ok:
                out.append(e)
        elif np.isfinite(s):
            out.append(e)
        if np.isfinite(s):
            hist.append(s)
    return out


def build_variant(events: list[dict], gated: list[dict]) -> list[dict]:
    """Les events machine d'une variante : hold/lev/fees + stamping
    expanding de la médiane d'ATR (doctrine PR-168)."""
    mae_gated = max(e["mae_adverse"] for e in gated)
    lev = levier_majors_safe(mae_gated)
    hist: list[float] = []
    out = []
    for e in gated:
        a = e["atr_pct"]
        med = float(np.median(hist)) if hist else a   # le 1er : ratio 1.0
        hist.append(a)
        e = dict(e)
        e.update({"strategy": "cascade_al", "lev": lev, "hold_h": HOLD_H,
                  "fee_rt_bps": TAKER_RT, "atr_med": med})
        out.append(e)
    return out


def sizer(e: dict, st=None) -> float:
    return min(max(0.24 * MACHINE_K * (e["atr_pct"] / e["atr_med"]),
                   0.08 * MACHINE_K), 0.40 * MACHINE_K)


def split_report(res: dict, boundary_ms: float) -> dict:
    tr = {"n": 0, "pnl": 0.0, "liq": 0, "win": 0}
    va = dict(tr)
    for t in res["trades"]:
        side = tr if t["entry_ts"].timestamp() * 1000 < boundary_ms else va
        side["n"] += 1
        side["pnl"] += t["pnl"]
        side["liq"] += 1 if t["liq"] else 0
        side["win"] += 1 if t["pnl"] > 0 else 0
    return tr, va


def fmt(tag: str, part: dict) -> str:
    roi = part["pnl"] / CAPITAL * 100.0
    wr = part["win"] / part["n"] * 100.0 if part["n"] else float("nan")
    liq = part["liq"] / part["n"] * 100.0 if part["n"] else float("nan")
    return (f"{tag}: n {part['n']:3d} · ROI {roi:+7.1f} % · "
            f"WR {wr:5.1f} % · liq {liq:5.1f} %")


def main() -> int:
    print("=== A/B SENS DU GATE AL (le wallet juge) ===", flush=True)
    regime = btc_regime_series()
    evs = collect_featured(regime, "majors")
    add_rolling_scores(evs)            # le score CORRIGÉ (PR-172)
    evs = [e for e in evs if np.isfinite(e.get("al_score", float("nan")))]
    evs.sort(key=lambda e: e["ts_ms"])
    boundary_ms = evs[int(len(evs) * 0.7)]["ts_ms"] / 1e6   # ns → ms
    fh = funding_hourly_all()
    print(f"events scorés : {len(evs)} · split 70/30 à "
          f"{boundary_ms / 86400000:.0f} j", flush=True)

    variants = {
        "HOT  (>= q66, gate actuel)": expanding_gate(evs, "hot"),
        "COLD (<= q33, inversé)     ": expanding_gate(evs, "cold"),
        "NONE (pas de gate)         ": list(evs),
    }
    for tag, gated in variants.items():
        if not gated:
            print(f"{tag} : vide")
            continue
        machine_ev = build_variant(evs, gated)
        res = run_stack(machine_ev, CAPITAL, sizer, fh)
        tr, va = split_report(res, boundary_ms)
        full_roi = (res["balance"] - CAPITAL) / CAPITAL * 100.0
        print(f"\n{tag}")
        print(f"  FULL : n {res['n']} · ROI {full_roi:+7.1f} % · "
              f"DD {res['max_dd']:5.1f} % · liqs {res['n_liq']}")
        print(f"  TRAIN {fmt('', tr)}")
        print(f"  VAL   {fmt('', va)}")
    print("\nDISCOVERY : train/val observés — jamais promote sans "
          "confirmation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
