#!/usr/bin/env python
"""VOL-SPIKE sur MEMECOINS — l'extension de l'univers (27/09).

vol_spike_6h (fade du range ≥ 4× médiane 14j, gate ATR-décile, hold 6h,
1x) est le seul flux P5 qui PASSE : validé CANDIDAT sur le run global
(+0,012 $/trade taker, corr cascade -0,22 = anti-corrélé, registre docs/20
27/09). Il n'a JAMAIS été testé sur l'univers MEMECOIN seul — le flux de
fréquence pourrait doubler si la mécanique tient sur l'autre univers.

EXTENSION, PAS OPTIMISATION : les seuils p5 sont INTOUCHÉS (hold 6h,
k_rng 4,0, abs_min 2,5 %, fenêtre 336h, gate ATR-décile). Deux variantes
honnêtes :
  A (primaire) — run natif meme : la mécanique p5 appliquée aux symboles
     non-MAJORS (même filtre d'univers que collect_meme), le décile ATR
     recalculé DANS l'univers (c'est la même mécanique, pas un re-tuning).
  B (sensibilité) — les events du run global p5 (gate global) filtrés
     sur l'univers meme : mesure la dépendance au référentiel du gate.

Mesures (harnais v5, run_stack — wallet séquentiel, entrée open t+1, un
créneau, MAE fenêtre, funding réel moyen, 1x flat 5 %) : N/an, WR,
espérance taker ET maker, MAE 6h mesuré AVANT de conclure (règle gravée
levier ≤ 100/(maxMAE+0,5) — si MAE max > 99,5 % le flux est MORT par
construction 0-liq), corr du PnL mensuel avec cascade MAJEURS et cascade
MEME (l'intérêt = la décorrélation). Si l'espérance est positive MAIS la
corr cascade_meme > 0,5 → PASS-doublon-inutile : le flux n'ajoute rien
au stack. Split train/val PAR LE TEMPS (70/30) en contrôle de stabilité
— aucun seuil ne bouge.

  .venv/bin/python scripts/volspike_meme_test.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.p5_frequency_test import (  # noqa: E402
    MAJORS, SIZE, collect_vol_spike, corr_months, guard_fous,
    machine_streams_flat, monthly_series, run_flat, stats_block)
from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
HOLD = 6                # hold 6h — le seul qui tient (vol_spike_12h FAIL)
K_RNG, ABS_MIN, WIN = 4.0, 2.5, 336   # seuils p5 INTOUCHÉS
LIQ_1X = 99.5           # à 1x la mort est à 99,5 % (règle 100/(MAE+0,5))


# ——————————————— le collecteur meme (mécanique p5 identique) ———————————————

def collect_vol_spike_meme(con: sqlite3.Connection, hold: int = HOLD,
                           k_rng: float = K_RNG, abs_min: float = ABS_MIN,
                           win: int = WIN, atr_gate: bool = True
                           ) -> list[dict]:
    """Vol-spike p5, VERBATIM, sur l'univers memecoin = les symboles 1h
    hors MAJORS (le même filtre d'univers que collect_meme de
    the_machine). Seule différence avec p5.collect_vol_spike : la liste
    de symboles. Le décile ATR est recalculé DANS l'univers."""
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol") if r[0] not in MAJORS]
    events: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < win + hold + 2:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens, highs, lows = df["open"].values, df["high"].values, df["low"].values
        close_s = df["close"]
        rng = (df["high"] - df["low"]) / close_s * 100
        med = rng.rolling(win, min_periods=100).median()
        sig = ((rng >= k_rng * med) & (rng >= abs_min)).fillna(False)
        body_up = (df["close"] >= df["open"]).values
        atr = (close_s.diff().abs().rolling(24).mean() / close_s * 100).values
        for t in np.where(sig)[0]:
            ei = t + 1
            if ei + hold >= len(idx_ns) or t < win:
                continue
            entry = opens[ei]
            if entry <= 0 or not np.isfinite(atr[ei]):
                continue
            exit_j = ei + hold - 1
            exit_px = df["close"].values[exit_j]
            if body_up[t]:                      # spike haussier → SHORT
                mae = (highs[ei:exit_j + 1].max() - entry) / entry * 100
                ret = (entry - exit_px) / entry * 100
                sign = 1
            else:                               # spike baissier → LONG
                mae = (entry - lows[ei:exit_j + 1].min()) / entry * 100
                ret = (exit_px - entry) / entry * 100
                sign = -1
            events.append({"sym": sym, "ts_ms": int(idx_ns[ei]),
                           "strategy": "vol_spike_meme", "lev": 1,
                           "hold_h": hold, "fee_rt_bps": TAKER_RT,
                           "entry": float(entry), "exit": float(exit_px),
                           "price_ret_short": ret,
                           "mae_adverse": float(max(mae, 0.0)),
                           "fund_sign": sign, "atr_pct": float(atr[ei]),
                           "side": "short" if sign == 1 else "long"})
    if atr_gate and events:
        p90 = float(np.nanquantile([e["atr_pct"] for e in events], 0.90))
        events = [e for e in events if e["atr_pct"] <= p90]
    events.sort(key=lambda e: e["ts_ms"])
    return events


# ————————————————————————————— mesures —————————————————————————————

def mae_block(evs: list[dict]) -> dict:
    maes = np.array([e["mae_adverse"] for e in evs])
    return {"max": float(maes.max()), "p99": float(np.quantile(maes, 0.99)),
            "p95": float(np.quantile(maes, 0.95)),
            "med": float(np.median(maes)),
            "n_liqrule": int((maes >= LIQ_1X).sum()),
            "lev_safe": 100.0 / (float(maes.max()) + 0.5)}


def train_val(mrows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split PAR LE TEMPS 70/30 sur les mois — contrôle de stabilité,
    aucun seuil ne bouge (extension, pas optimisation)."""
    ms = sorted(mrows, key=lambda r: r["month"])
    k = int(np.ceil(len(ms) * 0.7))
    return ms[:k], ms[k:]


def seg_stats(rows: list[dict], trades: list[dict]) -> dict:
    if not rows:
        return {"months": 0, "n": 0, "wr": float("nan"), "pnl": 0.0}
    ms = {r["month"] for r in rows}
    sel = [t for t in trades if t["exit_ts"].strftime("%Y-%m") in ms]
    return {"months": len(rows), "n": len(sel),
            "wr": (sum(t["pnl"] > 0 for t in sel) / len(sel) * 100)
            if sel else float("nan"),
            "pnl": float(sum(t["pnl"] for t in sel))}


def overlap_meme(evs: list[dict], meme: list[dict]) -> float:
    """% d'events vol_spike meme dont la fenêtre de détention CHEVAUCHE
    une position cascade_meme sur le MÊME symbole (le doublon mécanique)."""
    per_sym: dict[str, list[tuple[int, int]]] = {}
    for e in meme:
        per_sym.setdefault(e["sym"], []).append(
            (e["ts_ms"], e["ts_ms"] + 24 * 3600 * 10**9))
    n_hit = 0
    for e in evs:
        lo, hi = e["ts_ms"], e["ts_ms"] + e["hold_h"] * 3600 * 10**9
        if any(lo < ch and clo < hi for clo, ch in per_sym.get(e["sym"], [])):
            n_hit += 1
    return n_hit / max(len(evs), 1) * 100


def monthly_table(res: dict) -> list[str]:
    rows = monthly_rows(res["trades"], CAPITAL)
    rois = [r["roi"] for r in rows]
    neg = [r["month"] for r in rows if r["pnl"] < 0]
    out = ["| Mois | Trades | WR | Liq | PnL $ | ROI % |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['month']} | {r['n']} | "
                   f"{r['w'] / max(r['n'], 1) * 100:.0f} % | {r['liq']} "
                   f"| {r['pnl']:+.2f} | {r['roi']:+.1f} % |")
    out += ["", f"Pire mois {min(rois):+.1f} %, record {max(rois):+.1f} %, "
                f"négatifs : {', '.join(neg) if neg else 'aucun'} "
                f"({len(neg)}/{len(rows)})."]
    return out


def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    fh = funding_hourly_all()
    print("[vsm] réplique flat de la machine (cascade majors/meme/survivor)…")
    mach = machine_streams_flat(con, fh)
    mach_stats = {n: stats_block(run_flat([dict(e) for e in evs], fh,
                                          evs[0]["fee_rt_bps"] if evs
                                          else TAKER_RT, n), 12)
                  for n, evs in mach.items()}
    cascade_maj = monthly_series(mach_stats["cascade_10x"]["mrows"])
    cascade_mem = monthly_series(mach_stats["cascade_meme"]["mrows"])
    comp = dict(cascade_maj)
    for m, p in cascade_mem.items():
        comp[m] = comp.get(m, 0.0) + p
    for other in ("survivor_long",):
        for m, p in monthly_series(mach_stats[other]["mrows"]).items():
            comp[m] = comp.get(m, 0.0) + p

    print("[vsm] collecte vol_spike meme (variante A native)…")
    ev_a = collect_vol_spike_meme(con)
    print("[vsm] collecte vol_spike global p5 → filtrage meme (variante B)…")
    ev_b = [e for e in collect_vol_spike(con, hold=HOLD)
            if e["sym"] not in MAJORS]
    meme_cas = mach["cascade_meme"]
    con.close()

    variants = [("A_native", ev_a), ("B_gate_global", ev_b)]
    results: dict[str, dict] = {}
    for name, evs in variants:
        if not evs:
            results[name] = {"empty": True}
            continue
        m = mae_block(evs)
        for fee, fee_rt in (("taker", TAKER_RT), ("maker", MAKER_RT)):
            r = stats_block(run_flat([dict(e) for e in evs], fh, fee_rt,
                                     "vol_spike_meme"), 12)
            r["mae"] = m
            r["events"] = evs
            r["corr_majors"] = corr_months(monthly_series(r["mrows"]),
                                           cascade_maj)
            r["corr_meme"] = corr_months(monthly_series(r["mrows"]),
                                         cascade_mem)
            r["corr_comp"] = corr_months(monthly_series(r["mrows"]), comp)
            r["ovl_meme"] = overlap_meme(evs, meme_cas)
            tr, va = train_val(r["mrows"])
            r["train"] = seg_stats(tr, r["res"]["trades"])
            r["val"] = seg_stats(va, r["res"]["trades"])
            results[f"{name}_{fee}"] = r

    # ——— le rapport ———
    lines = [
        "# VOL-SPIKE sur MEMECOINS — l'extension de l'univers",
        f"{t0:%d/%m/%Y %H:%M} UTC — la mécanique p5 vol_spike_6h (fade du "
        f"range ≥ 4× médiane 14j et ≥ 2,5 %, gate ATR-décile, hold 6h, 1x) "
        f"appliquée à l'univers MEMECOIN (symboles 1h hors "
        f"MAJORS — même filtre que collect_meme). EXTENSION, pas "
        f"optimisation : seuils p5 intouchés. Harnais v5 (run_stack, "
        f"wallet séquentiel, entrée open t+1, 1 créneau, 1x flat "
        f"{SIZE*100:.0f} % marge, $100).",
        "",
        "Variante A = run natif meme (décile ATR recalculé dans l'univers) ; "
        "variante B = events du run global p5 filtrés meme (sensibilité au "
        "référentiel du gate).",
        "",
        "## MAE 6h mesuré AVANT de conclure (règle 0-liq : lev ≤ "
        "100/(maxMAE+0,5), la mort à 1x = 99,5 %)", "",
        "| Variante | N | MAE max | p99 | p95 | médiane | ≥ 99,5 % | lev sûr |",
        "|---|---|---|---|---|---|---|---|"]
    for name, evs in variants:
        if not evs:
            lines.append(f"| {name} | 0 | — | — | — | — | — | — |")
            continue
        m = mae_block(evs)
        dead = m["max"] >= LIQ_1X
        lines.append(
            f"| {name} | {len(evs)} | {m['max']:.1f} % | {m['p99']:.1f} % "
            f"| {m['p95']:.1f} % | {m['med']:.1f} % | {m['n_liqrule']} "
            f"| {m['lev_safe']:.2f}x" + (" — **MORT par construction 0-liq**"
                                         if dead else " → 1x tient") + " |")

    lines += ["", "## Les runs SEUL à 1x (wallet séquentiel run_stack)", "",
              "| Variante | Coûts | N | N/mois | WR | Espérance $ | % marge "
              "| Liq | ROI/an | DD |", "|---|---|---|---|---|---|---|---|---|---|"]
    for key, r in results.items():
        if r.get("empty"):
            continue
        lines.append(
            f"| {key} | {key.split('_')[-1]} | {r['n']} "
            f"| {r['trades_mo']:.1f} | {r['wr']:.1f} % | {r['exp']:+.3f} "
            f"| {r['exp_pct_margin']:+.2f} % | {r['res']['n_liq']} "
            f"| {r['roi']:+.1f} % | {r['res']['max_dd']:.1f} % |")

    lines += ["", "## LA CORRÉLATION (le point clé — l'intérêt est la "
              "DÉCORRÉLATION, pas le doublon)", "",
              "Réplique flat de la machine (baseline anti-dérive, mêmes "
              "collecteurs que the_machine). Chevauchement = % d'events "
              "dont la détention 6h recouvre une position cascade_meme sur "
              "le même symbole.", "",
              "| Variante | Corr cascade MAJEURS | Corr cascade MEME | Corr "
              "machine 3 flux | Chevauchement meme | Lecture |",
              "|---|---|---|---|---|---|"]
    for key, r in results.items():
        if r.get("empty") or not key.endswith("taker"):
            continue
        cm, cme = r["corr_meme"][0], r["corr_comp"][0]
        read = ("doublon de fréquence (corr meme > 0,5)" if cm > 0.5
                else "décorrelé des deux cascades" if cm < 0.3 else "mi-doublon")
        lines.append(
            f"| {key} | {r['corr_majors'][0]:+.2f} ({r['corr_majors'][1]:+.2f}) "
            f"| {cm:+.2f} ({r['corr_meme'][1]:+.2f}) | {cme:+.2f} "
            f"| {r['ovl_meme']:.0f} % | {read} |")

    lines += ["", "## TRAIN/VAL par le temps (70/30, contrôle de stabilité — "
              "aucun seuil bougé)", "",
              "| Variante | Segment | Mois | N | WR | PnL $ |",
              "|---|---|---|---|---|---|"]
    for key, r in results.items():
        if r.get("empty") or not key.endswith("taker"):
            continue
        for seg, s in (("TRAIN", r["train"]), ("VAL", r["val"])):
            lines.append(f"| {key} | {seg} | {s['months']} | {s['n']} "
                         f"| {s['wr']:.1f} % | {s['pnl']:+.2f} |")

    # ——— la courbe mensuelle du primaire ———
    key = "A_native_taker"
    if key in results and not results[key].get("empty"):
        lines += ["", "## BLOC STATS mensuel — variante A taker (le primaire)",
                  "", *monthly_table(results[key]["res"])]
        lines += ["", "| Mois | MACHINE (réplique 3 flux) | vol_spike_meme A |",
                  "|---|---|---|"]
        sA = monthly_series(results[key]["mrows"])
        for m in sorted(set(comp) | set(sA)):
            lines.append(f"| {m} | {comp.get(m, 0.0):+.2f} "
                         f"| {sA.get(m, 0.0):+.2f} |")

    # ——— le verdict ———
    lines += ["", "## VERDICT (PASS-flux-nouveau / PASS-doublon-inutile / "
              "FAIL)", ""]
    for name, _ in variants:
        rt, rm = results.get(f"{name}_taker"), results.get(f"{name}_maker")
        if not rt or rt.get("empty"):
            lines.append(f"- **{name}** : aucun event meme — FAIL")
            continue
        m = rt["mae"]
        exp_ok = (rt["exp"] > 0) or (rm["exp"] > 0)
        cm = rt["corr_meme"][0]
        freq_ok = rt["trades_mo"] >= 10
        why = []
        if m["max"] >= LIQ_1X:
            why.append(f"MAE max {m['max']:.1f} % ≥ 99,5 % — MORT par "
                       f"construction 0-liq")
        if rt["res"]["n_liq"]:
            why.append(f"{rt['res']['n_liq']} liq au wallet séquentiel")
        if not exp_ok:
            why.append("espérance ≤ 0 nette aux deux régimes de frais")
        if not freq_ok:
            why.append(f"fréquence {rt['trades_mo']:.1f}/mois < 10")
        if exp_ok and freq_ok and not why and cm > 0.5:
            verdict = "PASS-doublon-inutile"
            why.append(f"espérance positive MAIS corr cascade_meme {cm:+.2f} "
                       f"> 0,5 — le flux n'ajoute rien au stack")
        elif not why:
            verdict = "PASS-flux-nouveau"
        else:
            verdict = "FAIL"
        lines.append(
            f"- **{name}** : **{verdict}** — N {rt['n']} "
            f"({rt['trades_mo']:.1f}/mois), WR {rt['wr']:.1f} %, espérance "
            f"{rt['exp']:+.3f} $ taker / {rm['exp']:+.3f} $ maker, MAE max "
            f"{m['max']:.1f} % (lev sûr {m['lev_safe']:.2f}x), corr meme "
            f"{cm:+.2f} / majors {rt['corr_majors'][0]:+.2f}, chevauchement "
            f"meme {rt['ovl_meme']:.0f} %" + (f" — {'; '.join(why)}"
                                              if why else ""))

    # ——— garde-fous anti-dérive ———
    lines += ["", "## GARDE-FOUS ANTI-DÉRIVE (baseline)", ""]
    ok_all = True
    for key, r in results.items():
        if r.get("empty"):
            continue
        gc, gp = guard_fous(r["res"])
        ok = gc < 0.005 and gp < 0.01
        ok_all &= ok
        lines.append(f"- {key} : composé {gc*100:.3f} %, "
                     f"Somme PnL ${gp:.4f} — {'OK' if ok else '✗ BUG'}")
    for n in mach:
        gc, gp = guard_fous(mach_stats[n]["res"])
        ok = gc < 0.005 and gp < 0.01
        ok_all &= ok
        lines.append(f"- machine réplique {n} : composé {gc*100:.3f} %, "
                     f"Somme PnL ${gp:.4f} — {'OK' if ok else '✗ BUG'}")
    if not ok_all:
        lines += ["", "⚠ AU MOINS UN GARDE-FOU A ÉCHOUÉ — CHIFFRES NON "
                      "PUBLIABLES."]

    dt = (datetime.now(timezone.utc) - t0).total_seconds()
    lines += ["", "---",
              "Règle gravée : levier ≤ 100/(maxMAE + 0,5) — 0 liq sans "
              "exception. Le(s) verdict(s) rejoignent le registre "
              "docs/20 (VALIDÉ/CANDIDAT/CONTEXTE/NUL) — un nul honnête "
              "vaut mieux qu'un faux positif. Un backtest n'est jamais "
              "une preuve : le paper forward tranche.",
              "", f"Run {dt:.0f} s."]

    out = REPORTS / "volspike-meme-2026-09-27.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[vsm] rapport écrit : {out}")

    print("\n[vsm] ===== RÉSUMÉ =====")
    for name, _ in variants:
        rt, rm = results.get(f"{name}_taker"), results.get(f"{name}_maker")
        if not rt or rt.get("empty"):
            print(f"[vsm] {name}: AUCUN EVENT — FAIL")
            continue
        m = rt["mae"]
        cm = rt["corr_meme"][0]
        exp_ok = (rt["exp"] > 0) or (rm["exp"] > 0)
        if m["max"] >= LIQ_1X or rt["res"]["n_liq"] or not exp_ok \
                or rt["trades_mo"] < 10:
            v = "FAIL"
        elif cm > 0.5:
            v = "PASS-doublon-inutile"
        else:
            v = "PASS-flux-nouveau"
        print(f"[vsm] {name}: N={rt['n']} ({rt['trades_mo']:.1f}/mois) "
              f"WR={rt['wr']:.1f}% exp={rt['exp']:+.3f}$tk/{rm['exp']:+.3f}$mk "
              f"MAEmax={m['max']:.1f}% liq={rt['res']['n_liq']} "
              f"corr_majors={rt['corr_majors'][0]:+.2f} corr_meme={cm:+.2f} "
              f"ovl={rt['ovl_meme']:.0f}% → {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
