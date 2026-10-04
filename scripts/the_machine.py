#!/usr/bin/env python
"""LA MACHINE — le portefeuille officiel du projet, reproductible chaque nuit.

La frontière validée de la session du 25/09, codifiée :
  1. CASCADE MAJEURS 10x, gate AL p66, sizing VOL-INVERSE (base 24 %)
     — MAE max gated 7,84 % < ligne de mort 9,5 % → 0 liquidation
  2. CASCADE MEMECOINS 1x (levier mécanique : MAE max 224 %) — le flux
     de fréquence (285 trades/an, WR 51,5 %)
  3. SURVIVOR LONG 72h 1x (coins >90j au-dessus de leur prix-90j) — le
     flux long décorrelé (MAE max 94,5 % → 1x obligatoire)
  4. VOL-SPIKE REVERSION 6h 1x — EXPÉRIMENTAL, flag CLI --vol-spike
     (DÉFAUT OFF : la config officielle 3 flux reste bit-reproductible).
     Le seul flux P5 qui passe (p5_frequency_test 27/09) : fade du range
     ≥ 4× médiane 14j, gate ATR-décile, corr cascade -0,22 — la logique
     de signal est RÉUTILISÉE telle quelle (collect_vol_spike), seuils
     p5 non re-tunés.

Garde-fous : MAE monitor (levier sûr ≤ 100/(maxMAE+0,5)), composé des
mois vs balance finale, somme des PnL mensuels.

  .venv/bin/python scripts/the_machine.py
  .venv/bin/python scripts/the_machine.py --vol-spike   # 4e flux (test)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402
from scripts.portfolio_sim import KDB, MAJORS, btc_regime_series, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)

REPORTS = ROOT / "reports"

# ——— T8 (pré-enregistré 01/10/2026, reports/aster_machine_deep_regimes.md) ———
# L'état du moniteur MAE 6 majors est ÉCRIT pour asservir le levier cascade
# majors des consommateurs (paper_forward.py, qubo_forward_tracker.py).
# Règle gravée : levier ≤ 100/(MAE_pire_régime + 0,5) → 4x sur le cycle ;
# 10x SEULEMENT si lev_safe >= 10 dans cet état.
MAE_STATE = ROOT / "data" / "warehouse" / "mae_state.json"


def write_mae_state(mae_gated: float, lev_safe: float,
                    path: Path | None = None) -> None:
    """Écrit mae_state.json {mae_gated, lev_safe, updated_at} (UTC ISO).
    Tolérante aux échecs (disque/path) : le rapport ne doit JAMAIS être
    bloqué par l'écriture de l'état."""
    p = path if path is not None else MAE_STATE
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "mae_gated": round(float(mae_gated), 4),
            "lev_safe": round(float(lev_safe), 4),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }), encoding="utf-8")
    except Exception as exc:
        print(f"[machine] mae_state.json non écrit : {exc}")


def collect_meme(con: sqlite3.Connection) -> list[dict]:
    """Flux 2 : la cascade sur les memecoins (levier mécanique à calculer
    par l'appelant via la distribution MAE)."""
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol") if r[0] not in MAJORS]
    meme: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens, highs, closes = df["open"].values, df["high"].values, df["close"].values
        close_s = pd.Series(closes, index=df.index)
        r1 = close_s.pct_change() * 100
        ra = r1.abs()
        cas = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
               & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        atr = (close_s.diff().abs().rolling(24).mean() / close_s * 100).values
        for t in np.where(cas)[0]:
            ei = t + 1
            if ei + 24 >= len(idx_ns) or t < 200:
                continue
            entry = opens[ei]
            if entry <= 0 or not np.isfinite(atr[ei]):
                continue
            x = closes[ei + 23]
            meme.append({"sym": sym, "ts_ms": int(idx_ns[ei]),
                         "strategy": "cascade_meme", "lev": 1, "hold_h": 24,
                         "fee_rt_bps": MAKER_RT, "entry": entry,
                         "exit": float(x),
                         "price_ret_short": (entry - x) / entry * 100,
                         "fund_sign": 1,
                         "mae_adverse": (highs[ei:ei + 24].max() - entry)
                         / entry * 100, "atr_pct": float(atr[ei])})
    meme.sort(key=lambda e: e["ts_ms"])
    return meme


def levier_majors_safe(mae_gated: float, cap: float = 10.0) -> float:
    """La règle 0-liq plafonnée au cap machine : lev ≤ min(cap, 100/(MAE+0,5)).

    Le même calcul que write_mae_state, exposé pur pour le test — le cap
    ne bind que si le MAE gated dépasse 9,5 % (lev_safe < 10).
    """
    return min(cap, 100.0 / (mae_gated + 0.5))


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    # ——— flux 1 : cascade majeurs 10x, gated, vol-inverse ———
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = 10
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)
    # FIX 05/10 (bug-hunt) : gardes flux-vide — un max()/median()/nanquantile sur une
    # liste vide plantait le nocturne avant le rapport (marché calme = zéro pattern).
    # Flux non-vide : calculs bit-identiques.
    if not events:
        print("[machine] cascade majors vide ce soir (aucun event) — rapport abstenu")
        return 0
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan"))
         for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    if not gated:
        print("[machine] cascade majors gated vide ce soir — rapport abstenu")
        return 0
    med_majors = float(np.median([e["atr_pct"] for e in gated]))
    mae_gated = max(e["mae_adverse"] for e in gated)
    lev_safe = 100 / (mae_gated + 0.5)
    write_mae_state(mae_gated, lev_safe)   # l'état du moniteur MAE (T8)

    def size_cascade(e, st=None):
        return min(max(0.24 * (e["atr_pct"] / med_majors), 0.08), 0.40)
    # FIX lot1 (F5) : la machine appliquait 10x même quand son propre
    # lev_safe < 10 — le rapport affichait « BAISSER LE LEVIER » et
    # poussait quand même. La règle 0-liq plafonne, elle n'affiche pas.
    lev_majors = levier_majors_safe(mae_gated)
    for e in gated:
        e["lev"] = lev_majors

    # ——— flux 2 : cascade memecoins 1x (levier mécanique) ———
    meme = collect_meme(con)
    if not meme:
        print("[machine] cascade meme vide ce soir — rapport abstenu")
        return 0
    mae_meme = max(e["mae_adverse"] for e in meme)
    lev_meme = max(1, int(100 / (mae_meme + 0.5)))
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = lev_meme

    def size_meme(e, st=None):
        return min(max(0.10 * (e["atr_pct"] / med_meme), 0.02), 0.30)

    # ——— flux 3 : survivor long 72h 1x ———
    # + le FILTRE ATR extrême : le décile supérieur (les LAB — les ×520 qui
    # crashent -64 %) est écarté ; c'est lui qui portait le max-DD (26/09)
    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    if not surv:
        print("[machine] survivor long vide ce soir — rapport abstenu")
        return 0
    _p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    _n_extreme = len(surv)
    surv = [e for e in surv if e["atr_pct"] <= _p90]
    _n_extreme -= len(surv)
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT

    # ——— flux 4 (EXPÉRIMENTAL, --vol-spike) : vol-spike reversion 6h 1x ———
    # p5_frequency_test 27/09 : le seul flux de fréquence P5 qui passe
    # (N 820/an, WR 53,7 %, +0,012 $/trade taker, corr cascade -0,22).
    # Import LAZY : p5_frequency_test importe the_machine (collect_meme) —
    # un import module-top créerait un cycle. Flag OFF = zéro collecte, la
    # config officielle 3 flux reste bit-reproductible.
    VOL_SPIKE = "--vol-spike" in sys.argv
    spike: list[dict] = []
    med_spike = float("nan")
    mae_spike = 0.0
    if VOL_SPIKE:
        from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
        spike = collect_vol_spike(con, hold=6)   # seuils p5 : 4×/2,5 %/gate ATR
        for e in spike:
            e["strategy"] = "vol_spike_6h"
            e["lev"] = 1
            e["fee_rt_bps"] = TAKER_RT
        if spike:
            mae_spike = max(e["mae_adverse"] for e in spike)
            med_spike = float(np.median([e["atr_pct"] for e in spike]))

    # le facteur global K : la calibration du DD sur la cible (25 %)
    _K = 0.89
    # le tilt corrélation (×2/×0,5) : 0 mois négatif mais +6 pts de DD —
    # la variante agressive ; le défaut = la config spec (DD 24,8 %)
    CORR_TILT = "--corr-tilt" in sys.argv

    # le poids QUALITÉ : les trades au funding le plus BAS des 6 majeures
    # (l'offre réelle — WR 81 % backtest) sont surdimensionnés ×1,5
    funding_ts: dict[str, tuple[list, list]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = funding_ts.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    for e in gated:
        ranks, own = [], np.nan
        for s in MAJORS:
            ft = funding_ts.get(s)
            if not ft or len(ft[0]) < 5:
                continue
            pos = int(np.searchsorted(np.array(ft[0]), e["ts_ms"],
                                      side="right")) - 1
            if pos < 0:
                continue
            if s == e["sym"]:
                own = ft[1][pos]
            ranks.append(ft[1][pos])
        e["fund_rank"] = (float(np.mean(np.array(ranks) <= own))
                          if ranks and np.isfinite(own) else np.nan)

    # la CORRÉLATION croisée roulante des 6 majeures (le régime systémique) :
    # corrélation haute = tout tombe ensemble = les cascades continuent ;
    # corrélation basse = bruit idiosyncratique = elles rebondissent.
    _majors_dfs = {s: load_df(con, s) for s in MAJORS}
    _rets = {s: d["close"].pct_change().values for s, d in _majors_dfs.items()}
    _idx = _majors_dfs["BTCUSDT"].index.astype("datetime64[ns]").asi8
    con.close()

    all_ev = sorted(gated + meme + surv + spike, key=lambda e: e["ts_ms"])

    _WIN = 168
    for e in gated:
        bi = int(np.searchsorted(_idx, e["ts_ms"], side="left"))
        lo = bi - _WIN
        if lo < 0:
            e["corr"] = np.nan
            continue
        pairs = []
        for i in range(len(MAJORS)):
            for j in range(i + 1, len(MAJORS)):
                a, b = _rets[MAJORS[i]][lo:bi], _rets[MAJORS[j]][lo:bi]
                m = np.isfinite(a) & np.isfinite(b)
                if m.sum() > 100:
                    sa, sb = a[m] - np.mean(a[m]), b[m] - np.mean(b[m])
                    if np.std(sa) * np.std(sb) > 0:
                        pairs.append(np.mean(sa * sb) / (np.std(sa) * np.std(sb)))
        e["corr"] = float(np.mean(pairs)) if pairs else np.nan
    _c_hi = float(np.nanquantile(
        [e.get("corr", np.nan) for e in gated[:int(len(gated) * 0.7)]], 0.66))
    _c_lo = float(np.nanquantile(
        [e.get("corr", np.nan) for e in gated[:int(len(gated) * 0.7)]], 0.33))

    def machine_fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * _K * (e["atr_pct"] / med_majors), 0.08 * _K), 0.40 * _K)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                return min(s0 * 1.5, 0.50 * _K)
            if CORR_TILT:
                c = e.get("corr", np.nan)
                if np.isfinite(c):
                    if c > _c_hi:
                        s0 = min(s0 * 2.0, 0.50 * _K)
                    elif c < _c_lo:
                        s0 = max(s0 * 0.5, 0.05 * _K)
            return s0
        if s == "cascade_meme":
            return min(max(0.10 * _K * (e["atr_pct"] / med_meme), 0.02 * _K),
                       0.30 * _K)
        if s == "vol_spike_6h":
            # même sizing vol-inverse que les flux 1x (base machine 10 %)
            return min(max(0.10 * _K * (e["atr_pct"] / med_spike), 0.02 * _K),
                       0.30 * _K)
        return 0.20 * _K                # survivor long (1x = 0 risque de liq, le notional scale librement)

    r = run_stack(all_ev, CAPITAL, machine_fn, fh)
    mr = monthly_rows(r["trades"], CAPITAL)
    wr = r["n_wins"] / max(r["n"], 1) * 100
    roi = (r["balance"] / CAPITAL - 1) * 100

    prod = 1.0
    sum_pnl = 0.0
    for x in mr:
        prod *= (1 + x["roi"] / 100)
        sum_pnl += x["pnl"]
    gap_c = abs(prod - r["balance"] / CAPITAL)
    gap_p = abs(sum_pnl - (r["balance"] - CAPITAL))
    rois_m = [x["roi"] for x in mr]
    neg = sum(1 for x in rois_m if x < 0) if mr else 0
    rec = max(rois_m) if mr else 0.0
    worst = min(rois_m) if mr else 0.0

    _flux4 = (" + vol_spike_6h 1x (EXPÉRIMENTAL --vol-spike)" if VOL_SPIKE
              else "")
    lines = [
        "# LA MACHINE — le portefeuille officiel",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"cascade 10x (gate AL p66={q66:.2f}, vol-inverse base 24 %, "
        f"MAE gated {mae_gated:.2f} % → levier sûr {lev_safe:.1f}x) + "
        f"cascade memecoins {lev_meme}x + survivor 1x{_flux4}.", "",
        "## BLOC STATS OFFICIEL", "",
        "| Stat | Valeur |", "|---|---|",
        f"| Wallet initial → final | ${CAPITAL:,.0f} → **${r['balance']:,.2f}** |",
        f"| **ROI (1 an)** | **{roi:+.0f} %** |",
        f"| Max DD | {r['max_dd']:.1f} % |",
        f"| **Liquidations** | **{r['n_liq']}** |",
        f"| Trades / WR | {r['n']} / {wr:.1f} % |",
        f"| Mois : moyen / pire / record | {np.mean(rois_m):+.1f} % / "
        f"{worst:+.1f} % / {rec:+.1f} % ({neg} négatifs) |",
        f"| Frais + slippage payés | ${r['fees']:,.2f} |",
        f"| Funding net | ${r['funding']:+,.2f} |",
        f"| Garde-fou composé des mois | écart {gap_c*100:.3f} % "
        f"{'OK' if gap_c < 0.005 else '✗ BUG'} |",
        f"| Garde-fou somme PnL | écart ${gap_p:.4f} "
        f"{'OK' if gap_p < 0.01 else '✗ BUG'} |",
        "", "## LA TABLE MENSUELLE", "",
        "| Mois | Trades | WR | Liq | Balance début → fin | ROI |",
        "|---|---|---|---|---|---|",
    ]
    for x in mr:
        lines.append(
            f"| {x['month']} | {x['n']} | {x['w']/max(x['n'],1)*100:.0f} % "
            f"| {x['liq']} | ${x['start']:,.0f} → ${x['end']:,.0f} "
            f"| {x['roi']:+.1f} % |")
    lines += ["", "## LE MONITEUR MAE (la marge du 10x)", "",
              f"- MAE max gated : {mae_gated:.2f} % → levier sûr "
              f"{lev_safe:.1f}x {'OK — 10x tient' if lev_safe >= 10 else '⚠ BAISSER LE LEVIER'}",
              f"- MAE max memecoins : {mae_meme:.1f} % → levier {lev_meme}x",
              "", "Règle gravée : levier ≤ 100/(maxMAE + 0,5). La marge de",
              "sécurité est empirique (1 an) — le moniteur la garde."]
    if VOL_SPIKE:
        lines.append(f"- MAE max vol_spike_6h : {mae_spike:.1f} % → "
                     f"levier 1x (sûr ≤ {100 / (mae_spike + 0.5):.0f}x)")

    _sfx = "-volspike" if VOL_SPIKE else ""   # l'officiel 3 flux n'est jamais écrasé
    out = REPORTS / f"the-machine-{datetime.now(timezone.utc):%Y-%m-%d}{_sfx}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[machine] ${CAPITAL:,.0f} → ${r['balance']:,.2f} "
          f"({roi:+.0f} %/an), DD {r['max_dd']:.1f} %, liq {r['n_liq']}, "
          f"{r['n']} trades, record mois {rec:+.1f} %, {neg} mois négatifs"
          + (" | 4e flux vol_spike_6h ON" if VOL_SPIKE else ""))
    print(f"[machine] garde-fous : composé {gap_c*100:.3f} %, "
          f"PnL ${gap_p:.4f} | MAE gated {mae_gated:.2f} % "
          f"(levier sûr {lev_safe:.1f}x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
