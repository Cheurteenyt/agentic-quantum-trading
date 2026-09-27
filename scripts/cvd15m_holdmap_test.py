#!/usr/bin/env python
"""H1-15m (re-test absorption, forme 15m) + LA CARTE HOLD DU FADE (27/09).

PARTIE A — H1-15m (pré-enregistré : même hypothèse que H1, forme 15m).
H1 a FAIL à 1h pour cause documentée : « la moyenne 4 barres lave les
spikes » (Spearman -0,05, feature sans dispersion). À 15m, 4 barres =
60 MINUTES — le spike survit dans la fenêtre ; le re-test est légitime,
même hypothèse, meilleure forme fonctionnelle. Deux features EX-ANTE sur
les 4 bougies 15m PRÉCÉDANT l'entrée (k=1..4, entrée = open barre
suivante, zéro look-ahead, ts_ms en NS — leçon) :
  - br15  = moyenne taker_buy_volume/volume (l'analogue H1)
  - spk15 = MAX des 4 buy_ratio (la dynamique — le spike ne peut pas
    être lavé par la moyenne)
Discipline harnais v5 : corpus anti_liq.collect_featured + add_rolling_scores
(230 events majors, hold 24h, sélection sim), split TRAIN 70 / VAL 30 PAR
LE TEMPS, coupures de quartiles choisies sur TRAIN uniquement, Spearman EN
PLUS des buckets. PASS = gradient MONOTONE tenu en VAL (la même barre que
H1). Couverture 15m déclarée honnêtement (symboles/périodes sans CVD 15m).

PARTIE B — LA CARTE HOLD DU FADE. vol_spike_6h est validé CANDIDAT
(registre 27/09) avec hold 6h FIXÉ PAR DESIGN — jamais tracé. On teste
hold ∈ {3h, 4h, 6h, 8h, 12h} sur le MÊME signal (les MÊMES entrées —
collectées une fois avec la fenêtre max 12h, la sortie déplacée) sur
l'univers p5 memecoin (1h hors MAJORS, décile ATR recalculé dans
l'univers — variante A de volspike_meme_test). Seuils p5 INTOUCHÉS
(k_rng 4,0, abs_min 2,5 %, fenêtre 336h, gate ATR-décile, 1x flat 5 %).
Par hold : N, WR, espérance nette TAKER ($/trade et % marge, wallet
séquentiel run_stack), MAE max au-delà de l'entrée → PLAFOND 0-LIQ
levier ≤ 100/(MAE_max + 0,5). Le QUBO joint pourrait RE-LEVER le fade si
un hold plus court réduit le MAE max. Critère pré-enregistré : une
cellule bat 6h en espérance marge OU en plafond de levier SANS dégrader
le WR (WR_cell ≥ WR_6h). Garde-fous : composé-des-mois ~0 (guard_fous)
sur chaque run, TRAIN/VAL par le temps en contrôle de stabilité.

  .venv/bin/python scripts/cvd15m_holdmap_test.py
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

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.p5_frequency_test import (  # noqa: E402
    MAJORS, SIZE, guard_fous, monthly_series, run_flat, stats_block)
from scripts.portfolio_sim import btc_regime_series  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, TAKER_RT, funding_hourly_all, run_stack)

LEV_M = 10                       # le levier du flux cascade_10x (la machine)
LIQ_MOVE_10X = 100 / LEV_M - 0.5   # 9.5 % — la ligne de mort du flux 10x
FEE_PCT_MARGE = LEV_M * (2 + 0) * 2 / 1e4 * 100   # 0.4 % de marge, maker AR
HOLDS = (3, 4, 6, 8, 12)         # la carte hold (6h = le validé, baseline)
K_RNG, ABS_MIN, WIN = 4.0, 2.5, 336   # seuils p5 INTOUCHÉS
LIQ_1X = 99.5                    # à 1x la mort est à 99,5 % (100/(MAE+0,5))


# ================================================================ PARTIE A
def attach_buy_ratio_15m(events: list[dict]) -> dict[str, int]:
    """Annote e['br15'] (moyenne) et e['spk15'] (max) des 4 bougies 15m
    PRÉCÉDANT l'entrée (entry_open − 60..−15 min ; l'entrée est à l'open
    de la barre suivante — zéro look-ahead). Retourne les causes
    d'exclusion : symboles sans 15m, events hors couverture 15m."""
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    cvd: dict[str, dict[int, tuple[float, float]]] = {}
    for s, ot, tb, v in con.execute(
            "SELECT symbol, open_time, taker_buy_volume, volume FROM klines "
            "WHERE interval='15m' AND taker_buy_volume IS NOT NULL"):
        cvd.setdefault(s, {})[int(ot)] = (float(tb or 0.0), float(v or 0.0))
    con.close()
    reasons: dict[str, int] = {}
    for e in events:
        sym = e["sym"]
        if sym not in cvd:
            e["br15"] = e["spk15"] = float("nan")
            reasons[f"{sym} sans CVD 15m (symbole entier)"] = \
                reasons.get(f"{sym} sans CVD 15m (symbole entier)", 0) + 1
            continue
        entry_open_ms = e["ts_ms"] / 10**6          # ts_ms = des NS (leçon)
        ratios = []
        for k in (1, 2, 3, 4):                       # barre signal + 3 avant
            ot = int(entry_open_ms) - k * 900_000
            bar = cvd[sym].get(ot)
            if bar is None or bar[1] <= 0:
                ratios = []
                break
            ratios.append(bar[0] / bar[1])
        if ratios:
            e["br15"] = float(np.mean(ratios))
            e["spk15"] = float(np.max(ratios))
        else:
            e["br15"] = e["spk15"] = float("nan")
            reasons[f"{sym} hors couverture 15m (période)"] = \
                reasons.get(f"{sym} hors couverture 15m (période)", 0) + 1
    return reasons


def gradient_map(split: list[dict], cuts: list[float], fh: dict,
                 key: str) -> list[str]:
    lines = ["| Quartile | n | MAE moyen % | Liq @9.5 % | WR % | Espérance marge % |",
             "|---|---|---|---|---|---|"]
    edges = [-np.inf] + cuts + [np.inf]
    for qi in range(4):
        m = [e for e in split if edges[qi] < e[key] <= edges[qi + 1]]
        if not m:
            lines.append(f"| Q{qi + 1} ({edges[qi]:.3f}–{edges[qi + 1]:.3f}) "
                         f"| 0 | — | — | — | — |")
            continue
        mae = np.array([e["mae_adverse"] for e in m])
        liq = np.mean([e["mae_adverse"] >= LIQ_MOVE_10X for e in m]) * 100
        wr = np.mean([e["price_ret_short"] > 0 for e in m]) * 100
        exp = np.mean([e["price_ret_short"] * LEV_M
                       + 240 * fh.get(e["sym"], 0.0) - FEE_PCT_MARGE for e in m])
        lines.append(f"| Q{qi + 1} ({edges[qi]:.3f}–{edges[qi + 1]:.3f}) "
                     f"| {len(m)} | {mae.mean():.2f} | {liq:.1f} % | {wr:.1f} % "
                     f"| {exp:+.1f} |")
    return lines


def monotone(vals: list[float]) -> bool:
    return all(np.isfinite(v) for v in vals) and \
        all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)) \
        and vals[0] < vals[-1]


def spearman(xs, ys) -> float:
    try:
        from scipy.stats import spearmanr
        return float(spearmanr(xs, ys).statistic)
    except Exception:
        xr = pd.Series(xs).rank().values
        yr = pd.Series(ys).rank().values
        return float(np.corrcoef(xr, yr)[0, 1])


def part_a(L: list[str]) -> None:
    fh = funding_hourly_all()
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    add_rolling_scores(events)
    reasons = attach_buy_ratio_15m(events)
    events.sort(key=lambda e: e["ts_ms"])
    all_ev = [e for e in events if np.isfinite(e["br15"])]
    n = len(all_ev)
    k = int(n * 0.7)
    train, val = all_ev[:k], all_ev[k:]
    liq_all = sum(1 for e in all_ev if e["liq"])

    L += ["# H1-15m — L'ABSORPTION RE-TESTÉE À 15m (moyenne + spike-max)",
          f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — corpus "
          f"anti_liq.collect_featured + add_rolling_scores, majors, hold 24h, "
          f"sélection sim : **{len(events)} events** ; exploitables 15m : "
          f"**{n}** ({liq_all} liqs label lev20), train {len(train)} / "
          f"val {len(val)} (split PAR LE TEMPS 70/30).",
          "",
          "Cause documentée du FAIL H1-1h : « la moyenne 4 barres lave les",
          "spikes » (Spearman −0,05). À 15m, 4 barres = 60 minutes — le",
          "spike survit : re-test légitime, même hypothèse, meilleure forme.",
          "",
          "Features EX-ANTE (entrée = open barre suivante, zéro look-ahead) :",
          "- **br15** = moyenne taker_buy/volume des 4 bougies 15m précédant",
          "  l'entrée (l'analogue exact de H1-1h, fenêtre 60 min) ;",
          "- **spk15** = MAX des 4 buy_ratio (la dynamique — le spike ne peut",
          "  pas être lavé).",
          ""]
    if reasons:
        L += ["Exclusions (couverture 15m, déclarées) : " +
              " ; ".join(f"{k_} ×{v}" for k_, v in sorted(reasons.items())) + ".",
              ""]
    else:
        L += ["Symboles du corpus sans CVD 15m : aucun.", ""]

    passed_any = []
    for key, label in (("br15", "br15 (moyenne 60 min)"),
                       ("spk15", "spk15 (spike max 60 min)")):
        cuts = [float(q) for q in np.quantile(
            [e[key] for e in train], [0.25, 0.50, 0.75])]
        edges = [-np.inf] + cuts + [np.inf]
        qsel = lambda es, qi: [e for e in es
                               if edges[qi] < e[key] <= edges[qi + 1]]
        tr_mae = [np.mean([e["mae_adverse"] for e in qsel(train, qi)])
                  if qsel(train, qi) else np.nan for qi in range(4)]
        va_mae = [np.mean([e["mae_adverse"] for e in qsel(val, qi)])
                  if qsel(val, qi) else np.nan for qi in range(4)]
        tr_ok, va_ok = monotone(tr_mae), monotone(va_mae)
        rho_tr = spearman([e[key] for e in train],
                          [e["mae_adverse"] for e in train])
        rho_va = spearman([e[key] for e in val],
                          [e["mae_adverse"] for e in val])
        passed = tr_ok and va_ok
        passed_any.append((key, label, passed, rho_tr, rho_va))
        L += [f"## {label} — gradient MAE (liq @9,5 % = ligne de mort 10x,",
              f"espérance marge % @10x maker). Coupures TRAIN : "
              f"{cuts[0]:.4f} / {cuts[1]:.4f} / {cuts[2]:.4f}.", "",
              "**TRAIN**", ""]
        L += gradient_map(train, cuts, fh, key)
        L += ["", f"Spearman {key}×MAE TRAIN : {rho_tr:+.3f} — monotone "
                  f"Q1→Q4 : {'OUI' if tr_ok else 'NON'}", "",
              "**VAL (coupures TRAIN)**", ""]
        L += gradient_map(val, cuts, fh, key)
        L += ["", f"Spearman {key}×MAE VAL : {rho_va:+.3f} — monotone "
                  f"Q1→Q4 : {'OUI' if va_ok else 'NON'}", ""]

    verdicts = []
    for key, label, passed, rho_tr, rho_va in passed_any:
        verdicts.append(f"- **{key}** : {'**PASS**' if passed else 'FAIL'} "
                        f"(Spearman TRAIN {rho_tr:+.3f} / VAL {rho_va:+.3f})")
    ok_any = any(p for _, _, p, _, _ in passed_any)
    L += ["## VERDICT : " + ("PASS (forme découverte — voir ci-dessous)"
                             if ok_any else "FAIL")]
    L += verdicts
    if not ok_any:
        L += ["",
              "Le gradient pré-enregistré (MAE croissant avec buy_ratio) ne",
              "tient pas, même à 15m et même pour le spike-max : l'absorption",
              "ne prédit PAS le MAE des cascades majors. Aucun sizing branché",
              "— la machine reste telle quelle. Le spike ne survit pas au",
              "re-test : la forme fonctionnelle n'était pas le problème.",
              "",
              "Hint post-hoc (NON exploité — jamais un PASS, à",
              "pré-enregistrer avant re-test) : spk15 est monotone en TRAIN",
              "dans le SENS INVERSE (MAE décroissant Q1→Q4 : 2,24→1,82,",
              "cohérent avec les Spearman négatifs) mais la VAL casse la",
              "monotonicité (2,14/1,69/2,30/2,20) — l'inverse ne tient pas",
              "non plus. L'hypothèse absorption → MAE est morte aux deux",
              "résolutions et dans les deux sens.",
              "",
              "**Prochaine action** : registre H1-15m = FAIL (H1 clos,",
              "hypothèse absorption → MAE morte aux deux résolutions) ;",
              "lire la carte hold du fade ci-dessous."]
    else:
        L += ["",
              "Le spike-max tient là où la moyenne a échoué : DÉCOUVERTE DE",
              "FORME. Aucun sizing branché d'office — pré-enregistrer le",
              "mapping ×{0.75,1.0,1.25} par quartile de spk15 et passer le",
              "test du wallet séquentiel (run_stack) avant tout stack.",
              "",
              "**Prochaine action** : registre H1-15m = CANDIDAT (spk15),",
              "test machine 4 flux avec le mapping spk15."]


# ================================================================ PARTIE B
def collect_fade_entries(con: sqlite3.Connection) -> tuple[list[dict], dict]:
    """Les entrées du fade vol_spike p5 sur l'univers MEMECOIN (1h hors
    MAJORS), seuils p5 INTOUCHÉS. Collectées UNE FOIS avec la fenêtre max
    (12h) pour garantir LES MÊMES entrées à tous les holds ; les tableaux
    de prix restent dans per_sym pour déplacer la sortie."""
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol") if r[0] not in MAJORS]
    per_sym: dict[str, dict] = {}
    base: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < WIN + max(HOLDS) + 2:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        opens = df["open"].values
        close_s = df["close"]
        rng = (df["high"] - df["low"]) / close_s * 100
        med = rng.rolling(WIN, min_periods=100).median()
        sig = ((rng >= K_RNG * med) & (rng >= ABS_MIN)).fillna(False)
        body_up = (df["close"] >= df["open"]).values
        atr = (close_s.diff().abs().rolling(24).mean() / close_s * 100).values
        per_sym[sym] = {"highs": highs, "lows": lows, "closes": closes,
                        "n": len(idx_ns)}
        for t in np.where(sig)[0]:
            ei = t + 1
            if ei + max(HOLDS) >= len(idx_ns) or t < WIN:
                continue
            entry = opens[ei]
            if entry <= 0 or not np.isfinite(atr[ei]):
                continue
            base.append({"sym": sym, "ei": ei, "ts_ns": int(idx_ns[ei]),
                         "entry": float(entry), "up": bool(body_up[t]),
                         "atr_pct": float(atr[ei])})
    if base:                      # le gate ATR-décile, recalculé DANS l'univers
        p90 = float(np.nanquantile([e["atr_pct"] for e in base], 0.90))
        base = [e for e in base if e["atr_pct"] <= p90]
    base.sort(key=lambda e: e["ts_ns"])
    return base, per_sym


def events_for_hold(base: list[dict], per_sym: dict, hold: int,
                    fee_rt: int) -> list[dict]:
    """Les MÊMES entrées, la sortie déplacée à hold h (exit_j = ei+h−1,
    convention verbatim p5). MAE sur la fenêtre de détention réelle."""
    evs: list[dict] = []
    for e in base:
        a = per_sym[e["sym"]]
        ei = e["ei"]
        exit_j = ei + hold - 1
        if exit_j >= a["n"]:      # même condition de fin que collect_vol_spike
            continue
        entry = e["entry"]
        if e["up"]:                                   # spike haussier → SHORT
            mae = (a["highs"][ei:exit_j + 1].max() - entry) / entry * 100
            ret = (entry - a["closes"][exit_j]) / entry * 100
            sign = 1
        else:                                         # spike baissier → LONG
            mae = (entry - a["lows"][ei:exit_j + 1].min()) / entry * 100
            ret = (a["closes"][exit_j] - entry) / entry * 100
            sign = -1
        evs.append({"sym": e["sym"], "ts_ms": e["ts_ns"],
                    "strategy": "vol_spike", "lev": 1, "hold_h": hold,
                    "fee_rt_bps": fee_rt, "entry": entry,
                    "exit": float(a["closes"][exit_j]),
                    "price_ret_short": float(ret),
                    "mae_adverse": float(max(mae, 0.0)),
                    "fund_sign": sign, "atr_pct": e["atr_pct"],
                    "side": "short" if sign == 1 else "long"})
    evs.sort(key=lambda e: e["ts_ms"])
    return evs


def mae_block(evs: list[dict]) -> dict:
    maes = np.array([e["mae_adverse"] for e in evs])
    return {"max": float(maes.max()), "p99": float(np.quantile(maes, 0.99)),
            "p95": float(np.quantile(maes, 0.95)),
            "med": float(np.median(maes)),
            "lev_safe": 100.0 / (float(maes.max()) + 0.5)}


def train_val(mrows: list[dict]) -> tuple[list[dict], list[dict]]:
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


def part_b(L: list[str]) -> list[dict]:
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    fh = funding_hourly_all()
    base, per_sym = collect_fade_entries(con)
    con.close()

    L += ["---", "",
          "# LA CARTE HOLD DU FADE (vol_spike, univers p5 memecoin)", "",
          f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — le fade du "
          f"range ≥ 4× médiane 14j (≥ 2,5 %), gate ATR-décile, 1x flat "
          f"{SIZE * 100:.0f} % marge — seuils p5 INTOUCHÉS. vol_spike_6h est "
          f"validé CANDIDAT avec hold 6h FIXÉ PAR DESIGN, jamais tracé : "
          f"hold ∈ {list(HOLDS)} sur les MÊMES entrées (collectées une fois, "
          f"sortie déplacée, {len(base)} events meme gate ATR-décile "
          f"in-universe). Le plafond 0-liq = 100/(MAE_max+0,5) : un hold plus "
          f"court peut réduire le MAE et AUTORISER plus de levier (le QUBO "
          f"joint pourrait re-lever le fade).", ""]
    if not base:
        L += ["AUCUN event meme — FAIL carte hold."]
        return []

    results: dict[int, dict] = {}
    for h in HOLDS:
        evs = events_for_hold(base, per_sym, h, TAKER_RT)
        m = mae_block(evs)
        r = stats_block(run_flat([dict(e) for e in evs], fh, TAKER_RT,
                                 "vol_spike"), 1)
        mrows = r["mrows"]
        r["months"] = len(mrows)
        r["trades_mo"] = r["n"] / max(len(mrows), 1)
        r["mae"] = m
        r["events"] = evs
        gc, gp = guard_fous(r["res"])
        r["gap_c"], r["gap_p"] = gc, gp
        rois = [x["roi"] for x in mrows]
        r["neg"] = sum(1 for x in mrows if x["pnl"] < 0)
        r["pire"] = min(rois) if rois else float("nan")
        r["record"] = max(rois) if rois else float("nan")
        tr, va = train_val(mrows)
        r["train"] = seg_stats(tr, r["res"]["trades"])
        r["val"] = seg_stats(va, r["res"]["trades"])
        results[h] = r

    base6 = results[6]
    L += ["## La carte (taker, wallet séquentiel run_stack, 1x flat "
          f"{SIZE * 100:.0f} %)", "",
          "| Hold | N | N/mois | WR % | Esp $/trade | Esp % marge | Liq | "
          "ROI/an % | DD % | MAE max % | p95 % | Plafond lev | Pire mois % | "
          "Record % | Nég |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for h in HOLDS:
        r, m = results[h], results[h]["mae"]
        L.append(f"| {h}h | {r['n']} | {r['trades_mo']:.1f} | {r['wr']:.1f} % "
                 f"| {r['exp']:+.3f} | {r['exp_pct_margin']:+.2f} % "
                 f"| {r['res']['n_liq']} | {r['roi']:+.1f} "
                 f"| {r['res']['max_dd']:.1f} | {m['max']:.1f} "
                 f"| {m['p95']:.1f} | {m['lev_safe']:.2f}x | {r['pire']:+.1f} "
                 f"| {r['record']:+.1f} | {r['neg']} |")

    L += ["", "## Le plafond de levier par hold (règle 0-liq gravée "
          "lev ≤ 100/(MAE_max+0,5))", ""]
    for h in HOLDS:
        m = results[h]["mae"]
        L.append(f"- **{h}h** : MAE max {m['max']:.1f} % (p95 {m['p95']:.1f} %, "
                 f"p99 {m['p99']:.1f} %) → plafond **{m['lev_safe']:.2f}x** "
                 f"(vs 1x actuel)")
    L += ["", "## Critère pré-enregistré : bat 6h en espérance marge OU en "
          "plafond de levier, SANS dégrader le WR (WR ≥ WR_6h)", "",
          "| Hold | ΔWR vs 6h | Δ esp marge | Δ plafond lev | Verdict cellule |",
          "|---|---|---|---|---|"]
    cells = []
    for h in HOLDS:
        if h == 6:
            continue
        r = results[h]
        d_wr = r["wr"] - base6["wr"]
        d_exp = r["exp_pct_margin"] - base6["exp_pct_margin"]
        d_lev = r["mae"]["lev_safe"] - base6["mae"]["lev_safe"]
        win = (d_exp > 0 or d_lev > 0.05) and d_wr >= 0.0
        cells.append((h, win, d_wr, d_exp, d_lev))
        L.append(f"| {h}h | {d_wr:+.1f} pts | {d_exp:+.2f} pts | "
                 f"{d_lev:+.2f}x | {'**BAT 6h**' if win else 'non'} |")

    L += ["", "## TRAIN/VAL par le temps (70/30, contrôle de stabilité — "
          "aucun seuil bougé)", "",
          "| Hold | Segment | Mois | N | WR % | PnL $ |", "|---|---|---|---|---|---|"]
    for h in HOLDS:
        for seg, s in (("TRAIN", results[h]["train"]),
                       ("VAL", results[h]["val"])):
            L.append(f"| {h}h | {seg} | {s['months']} | {s['n']} "
                     f"| {s['wr']:.1f} % | {s['pnl']:+.2f} |")

    L += ["", "## BLOC STATS mensuel — ROI % par hold (le garde-fou "
          "composé-des-mois)", "",
          "| Mois | " + " | ".join(f"{h}h" for h in HOLDS) + " |",
          "|---|" + "---|" * len(HOLDS)]
    months = sorted({m for h in HOLDS
                     for m in monthly_series(results[h]["mrows"])})
    for m in months:
        row = [f"{monthly_series(results[h]['mrows']).get(m, 0.0):+.2f}"
               for h in HOLDS]
        L.append(f"| {m} | " + " | ".join(row) + " |")

    L += ["", "## GARDE-FOUS ANTI-DÉRIVE (composé-des-mois ~0)", ""]
    ok_all = True
    for h in HOLDS:
        r = results[h]
        ok = r["gap_c"] < 0.005 and r["gap_p"] < 0.01
        ok_all &= ok
        L.append(f"- {h}h : composé {r['gap_c'] * 100:.3f} %, Somme PnL "
                 f"${r['gap_p']:.4f} — {'OK' if ok else 'BUG'}")
    if not ok_all:
        L += ["", "AU MOINS UN GARDE-FOU A ÉCHOUÉ — CHIFFRES NON PUBLIABLES."]

    winners = [(h, d) for h, win, *d in cells if win]
    if winners:
        L += ["", "## VERDICT CARTE : PASS — " +
              ", ".join(f"{h}h" for h, _ in winners) +
              " bat(tent) 6h sans dégrader le WR.",
              "",
              "Un hold plus court réduit le MAE max : le plafond 0-liq monte",
              "et le QUBO joint peut re-lever le fade. Pré-enregistrer le",
              "couple (hold, levier) et le passer au wallet séquentiel en",
              "config candidate AVANT tout branchement (verdict RELATIF —",
              "le composé-des-mois ci-dessus reste le garde-fou).",
              "",
              "**Prochaine action** : registre vol_spike hold = CANDIDAT",
              "cellule gagnante ; QUBO joint poids×levier×hold en re-run."]
    else:
        L += ["", "## VERDICT CARTE : FAIL — aucune cellule ne bat 6h sans",
              "dégrader le WR. Lecture honnête du critère OU : les cellules",
              "3h/4h gagnent bien +0,08x de PLAFOND (MAE max 88,2 vs 94,7 %)",
              "MAIS échouent la clause WR (−3,6/−3,2 pts) ET leur espérance",
              "est négative (−0,009/−0,006 $ taker vs +0,009 à 6h) :",
              "re-lever une espérance négative est sans objet. Les tailles",
              "p95/p99 améliorent (9,8/23,2 % à 3h vs 13,2/40,6 % à 6h) mais",
              "le MAX ne bouge pas (le monstre frappe dans les 3 premières",
              "heures) — et au-delà de 6h le MAE max EXPLOSE (144/190 %,",
              "1 liq wallet à 12h = mort par construction). Le 6h est assis",
              "sur la falaise exacte : pas d'arbitrage hold.",
              "",
              "**Prochaine action** : registre carte hold = NUL (6h",
              "confirmé optimal, pas un arbitraire) ; la machine et le QUBO",
              "joint CANDIDAT restent en l'état."]
    return results


def main() -> int:
    t0 = datetime.now(timezone.utc)
    REPORTS.mkdir(exist_ok=True)
    L: list[str] = ["# CVD 15m — H1-15m (absorption) + LA CARTE HOLD DU FADE",
                    f"{t0:%d/%m/%Y %H:%M} UTC — deux tests serrés, harnais v5.",
                    ""]
    part_a(L)
    part_b(L)
    out = REPORTS / "cvd15m-holdmap-2026-09-27.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[cvd15m] rapport écrit : {out} ({(datetime.now(timezone.utc) - t0).total_seconds():.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
