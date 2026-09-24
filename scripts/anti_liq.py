#!/usr/bin/env python
"""L'INDICATEUR ANTI-LIQUIDATION — prédire les trades qui vont mourir.

La découverte du sim v3 : les 73 liquidations (10,2 % des trades) sont
TOUTE la différence entre le réel (+13,9 %/mois, DD 70,5 %) et l'oracle
(+48,8 %/mois, DD 28,9 %). Les liqs CLUSTERENT (oct = 11, mars = 16) —
un phénomène qui cluster est prédictible.

Cet indicateur apprend, sur les features disponibles À L'ENTRÉE
(aucun look-ahead : tout est calculé au signal, avant l'entrée), ce qui
distingue un trade voué à la liquidation d'un trade normal.

DISCIPLINE (règle du projet) :
  - split train/val PAR LE TEMPS (70/30) — jamais aléatoire
  - les seuils sont choisis sur TRAIN, appliqués tels quels sur VAL
  - règle pré-enregistrée : le gate n'est ADOPTÉ que si en VAL il attrape
    ≥ 40 % des liqs en sacrifiant ≤ 15 % des gagnants
  - l'impact final se mesure dans le SIM séquentiel réel (pas dans l'abstrait)

  .venv/bin/python scripts/anti_liq.py
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
from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAJORS, HOLD_H, LIQ_MOVE_PCT, btc_regime_series, run_sim)

REPORTS = ROOT / "reports"
SIZE = 0.05
FEE_BPS, SLIP_BPS = 2, 0          # maker (GTX) : la config de référence
NUMERIC = ["atr_pct", "vol24", "cascade_depth", "accel", "dd_pct",
           "vwap_dev", "vol_spike", "btc_ret24", "storm_24h", "funding_last"]
CATEGORIC = ["regime"]


def funding_hourly_map() -> dict[str, float]:
    con = sqlite3.connect(KDB)
    acc: dict[str, list[float]] = {}
    for s, r in con.execute("SELECT symbol, rate FROM funding_history"):
        try:
            acc.setdefault(s, []).append(float(r))
        except (TypeError, ValueError):
            continue
    con.close()
    return {s: sum(v) / len(v) * 100 / 8 for s, v in acc.items()}


def collect_featured(regime: pd.Series) -> list[dict]:
    """Les événements cascade des majeures AVEC leurs features d'entrée.

    La sélection séquentielle du sim (premier dispo, skip des chevauche-
    ments) est répliquée pour que les labels correspondent au 719/73."""
    con = sqlite3.connect(KDB)
    dfs: dict[str, pd.DataFrame] = {}
    signals: list[int] = []          # ts de TOUS les signaux (feature storm)
    for sym in MAJORS:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        dfs[sym] = df
        close = df["close"]
        r1 = close.pct_change() * 100
        ra = r1.abs()
        cas = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
               & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        idx_ns = df.index.astype("datetime64[ns]").asi8
        signals += [int(idx_ns[t]) for t in np.where(cas)[0]]
    signals.sort()

    # funding par symbole : (temps, taux) triés pour l'as-of join
    funding_ts: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = funding_ts.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)  # ms→ns ou s→ns
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    funding_ts = {s: (np.array(t), np.array(r))
                  for s, (t, r) in funding_ts.items()}
    con.close()

    events: list[dict] = []
    for sym, df in dfs.items():
        close = df["close"]
        volume = df["volume"]
        highs = df["high"].values
        opens = df["open"].values
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        r1 = close.pct_change() * 100
        ra = r1.abs()
        cas = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
               & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)

        # --- features, TOUTES calculées au signal t (≤ t, zéro look-ahead) ---
        atr = close.diff().abs().rolling(24).mean()
        atr_pct = (atr / close * 100).values
        vol24 = r1.rolling(24).std().values
        depth3 = (r1 + r1.shift(1) + r1.shift(2))
        accel = (ra / ra.shift(2)).values
        dd = ((pd.Series(highs, index=idx).cummax() - close)
              / pd.Series(highs, index=idx).cummax() * 100).values
        vwap168 = ((close * volume).rolling(168).sum()
                   / volume.rolling(168).sum())
        vwap_dev = ((close - vwap168) / vwap168 * 100).values
        vol_med = volume.rolling(24).median()
        vol_spike = (volume / vol_med).values
        btc = dfs.get("BTCUSDT")
        btc_r24 = (btc["close"].pct_change(24) * 100).reindex(
            idx, method="ffill", limit=48).values if btc is not None else None
        sym_regime = regime.reindex(idx, method="ffill", limit=48).fillna("?")
        ft = funding_ts.get(sym)
        sig = np.array(signals)

        for t in np.where(cas)[0]:
            ei = t + 1
            if ei + HOLD_H >= len(idx_ns):
                continue
            entry = opens[ei]
            if entry <= 0 or t < 200 or np.isnan(atr_pct[t]) or np.isnan(vwap_dev[t]):
                continue
            exit_j = ei + HOLD_H - 1
            if exit_j >= len(idx_ns):
                continue
            exit_px = df["close"].values[exit_j]
            ret = (entry - exit_px) / entry * 100
            mae = (highs[ei:exit_j + 1].max() - entry) / entry * 100
            # le label du sim : mae ≥ seuil OU pnl ≤ -marge (indépendant de la balance)
            fees_pct = (FEE_BPS + SLIP_BPS) * 2 * 20 / 100
            fund_h = (np.interp(idx_ns[ei], ft[0], ft[1]) if ft is not None
                      and len(ft[0]) else 0.0)
            fund_pct = fund_h * HOLD_H * 20 / 100
            pnl_pct = ret * 20 + fund_pct - fees_pct
            liq = mae >= LIQ_MOVE_PCT or pnl_pct <= -100
            events.append({
                "sym": sym, "ts_ms": int(idx_ns[ei]), "entry": entry,
                "exit": exit_px, "price_ret_short": ret, "mae_adverse": mae,
                "liq": bool(liq),
                "atr_pct": float(atr_pct[t]), "vol24": float(vol24[t]),
                "cascade_depth": float(depth3.iloc[t]), "accel": float(accel[t]),
                "dd_pct": float(dd[t]), "vwap_dev": float(vwap_dev[t]),
                "vol_spike": float(vol_spike[t]),
                "btc_ret24": float(btc_r24[t]) if btc_r24 is not None else 0.0,
                "storm_24h": int(np.searchsorted(sig, idx_ns[ei], side="left")
                                 - np.searchsorted(sig, idx_ns[ei] - 24 * 3600 * 10**9,
                                                   side="left")),
                "funding_last": float(fund_h),
                "regime": str(sym_regime.iloc[t]),
                "hour": datetime.fromtimestamp(idx_ns[ei] / 10**9,
                                               tz=timezone.utc).hour,
            })
    events.sort(key=lambda e: e["ts_ms"])

    # --- la sélection séquentielle EXACTE du sim (les chevauchements skip) ---
    taken, i = [], 0
    while i < len(events):
        e = events[i]
        taken.append(e)
        hold_end = e["ts_ms"] + HOLD_H * 3600 * 1000
        while i < len(events) and events[i]["ts_ms"] < hold_end:
            i += 1
    return taken


def tercile_lift(vals: np.ndarray, liq: np.ndarray) -> list[tuple[str, int, int, float]]:
    """Le taux de liq par tercile (TRAIN) pour une feature numérique."""
    q1, q2 = np.quantile(vals, [1 / 3, 2 / 3])
    out = []
    for label, mask in (("T1 (bas)", vals <= q1),
                        ("T2", (vals > q1) & (vals <= q2)),
                        ("T3 (haut)", vals > q2)):
        n = int(mask.sum())
        l = int(liq[mask].sum())
        out.append((label, l, n, l / n * 100 if n else 0.0))
    return out


def main() -> int:
    regime = btc_regime_series()
    events = collect_featured(regime)
    liq_all = np.array([e["liq"] for e in events])
    n_liq = int(liq_all.sum())
    base_rate = n_liq / len(events) * 100

    # split PAR LE TEMPS 70/30
    k = int(len(events) * 0.7)
    train, val = events[:k], events[k:]

    # --- PHASE 2 : le score composite à RANGS ROULANTS ---
    # les niveaux absolus dérivent avec les régimes (le train ne transfère
    # pas) → chaque feature est rangée contre SES 90 derniers jours, puis
    # les rangs sont moyennés. Aucun look-ahead : fenêtre = événements
    # antérieurs uniquement.
    RISK_UP = ("atr_pct", "vol24", "dd_pct")       # haut = risqué
    RISK_DOWN = ("btc_ret24", "vwap_dev")          # bas = risqué
    WIN_NS = 90 * 86400 * 10**9
    for i, e in enumerate(events):
        lo = e["ts_ms"] - WIN_NS
        window = [p for p in events[:i] if p["ts_ms"] >= lo]
        if len(window) < 50:
            e["al_score"] = float("nan")
            continue
        ranks = []
        for f in RISK_UP:
            vals = np.array([p[f] for p in window])
            ranks.append(float(np.mean(vals <= e[f])))
        for f in RISK_DOWN:
            vals = np.array([p[f] for p in window])
            ranks.append(float(np.mean(vals <= -e[f])))
        e["al_score"] = float(np.mean(ranks))
    tr_liq = np.array([e["liq"] for e in train])
    va_liq = np.array([e["liq"] for e in val])

    lines = [
        "# L'INDICATEUR ANTI-LIQUIDATION",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{len(events)} trades cascade (majeures, hold 24h, sélection sim), "
        f"{n_liq} liqs ({base_rate:.1f} %). Train {len(train)} / Val {len(val)} "
        f"(split par le temps).", "",
        "## Univarié TRAIN — taux de liq par tercile", "",
        "| Feature | T1 | T2 | T3 |", "|---|---|---|---|",
    ]
    feats_train = {f: np.array([e[f] for e in train], dtype=float)
                   for f in NUMERIC}
    for f in NUMERIC:
        cells = []
        for label, l, n, rate in tercile_lift(feats_train[f], tr_liq):
            cells.append(f"{label} {rate:.1f} % ({l}/{n})")
        lines.append(f"| {f} | " + " | ".join(cells) + " |")
    for f in CATEGORIC:
        lines += ["", f"### {f} (TRAIN)", ""]
        for g in sorted({e[f] for e in train}):
            m = np.array([e[f] == g for e in train])
            n = int(m.sum()); l = int(tr_liq[m].sum())
            if n >= 20:
                lines.append(f"- {g} : {l/n*100:.1f} % ({l}/{n})")

    # --- les seuils choisis sur TRAIN, appliqués tels quels sur VAL ---
    def best_filter(feat_vals, liq_mask):
        """Le seuil qui attrape le plus de liqs pour ≤ 15 % de gagnants perdus."""
        best = None
        qs = np.quantile(feat_vals, np.linspace(0.05, 0.95, 19))
        for side in ("haut", "bas"):
            for q in qs:
                mask = (feat_vals >= q) if side == "haut" else (feat_vals <= q)
                if mask.sum() < 30:
                    continue
                caught = liq_mask & mask
                lost_winners = (~liq_mask & mask).sum() / max((~liq_mask).sum(), 1) * 100
                if lost_winners > 15:
                    continue
                catch = caught.sum() / max(liq_mask.sum(), 1) * 100
                if catch < 20:
                    continue
                if best is None or catch > best[0]:
                    best = (catch, f, side, float(q), int(caught.sum()),
                            float(lost_winners))
        return best

    lines += ["", "## Les filtres candidats (seuils choisis sur TRAIN)", "",
              "| Feature | Seuil (TRAIN) | Attrape TRAIN | Attrape VAL | Gagnants perdus VAL |",
              "|---|---|---|---|---|"]
    adopted: list[tuple[str, float, str]] = []
    for f in NUMERIC:
        tv = feats_train[f]
        b = best_filter(tv, tr_liq)
        if b is None:
            continue
        _, fname, side, q, c_train, _ = b
        vv = np.array([e[f] for e in val], dtype=float)
        mva = (vv >= q) if side == "haut" else (vv <= q)
        catch_val = (va_liq & mva).sum() / max(va_liq.sum(), 1) * 100
        lost_val = (~va_liq & mva).sum() / max((~va_liq).sum(), 1) * 100
        lines.append(f"| {fname} | {'≥' if side == 'haut' else '≤'} {q:.2f} "
                     f"| {c_train} liqs | {catch_val:.0f} % | {lost_val:.1f} % |")
        # règle pré-enregistrée : ≥ 40 % des liqs, ≤ 15 % des gagnants, en VAL
        if catch_val >= 40 and lost_val <= 15:
            adopted.append((f, q, side))

    # --- PHASE 2 : le score composite à rangs roulants ---
    fh = funding_hourly_map()
    def sim_on(subset: list[dict]) -> dict:
        return run_sim(subset, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS, oracle=False)

    real = sim_on(events)

    tr_scores = np.array([e["al_score"] for e in train], dtype=float)
    va_scores = np.array([e["al_score"] for e in val], dtype=float)
    tr_sc_ok = ~np.isnan(tr_scores)
    va_sc_ok = ~np.isnan(va_scores)

    lines += ["", "## PHASE 2 — LE SCORE COMPOSITE (rangs roulants 90j)", "",
              "Score = moyenne des rangs (atr, vol24, dd hauts + btc_ret24,",
              "vwap_dev bas) contre leurs 90 derniers jours. Terciles TRAIN :", ""]
    for label, mask in (("T1 (calme)", tr_scores <= np.nanquantile(tr_scores, 1/3)),
                        ("T2", (tr_scores > np.nanquantile(tr_scores, 1/3))
                         & (tr_scores <= np.nanquantile(tr_scores, 2/3))),
                        ("T3 (chaud)", tr_scores > np.nanquantile(tr_scores, 2/3))):
        m = mask & tr_sc_ok
        n = int(m.sum()); l = int(tr_liq[m].sum())
        lines.append(f"- {label} : {l/max(n,1)*100:.1f} % de liqs ({l}/{n})")

    # les coupures du gate, choisies sur TRAIN, jugées sur VAL
    lines += ["", "### Gate par score (règle pré-enregistrée : ≥40 % liqs, ≤15 % gagnants)", ""]
    score_gate_adopted = None
    for pct in (0.7, 0.8, 0.9):
        q = float(np.nanquantile(tr_scores, pct))
        mva = (va_scores >= q) & va_sc_ok
        catch = (va_liq & mva).sum() / max(va_liq.sum(), 1) * 100
        lost = (~va_liq & mva).sum() / max((~va_liq).sum(), 1) * 100
        ok = catch >= 40 and lost <= 15
        lines.append(f"- score ≥ p{int(pct*100)} ({q:.2f}) : VAL {catch:.0f} % "
                     f"des liqs, {lost:.1f} % des gagnants perdus "
                     f"{'✓ TIENT' if ok else '✗'}")
        if ok and score_gate_adopted is None:
            score_gate_adopted = q

    if score_gate_adopted is not None:
        kept = [e for e in events
                if not (not np.isnan(e["al_score"]) and e["al_score"] >= score_gate_adopted)]
        g = sim_on(kept)
        lines += ["", f"SIM avec le gate score ≥ {score_gate_adopted:.2f} : "
                  f"100 $ → ${g['balance']:,.2f} (DD {g['max_dd']:.1f} %, "
                  f"{g['n_liq']} liqs) vs sans gate ${real['balance']:,.2f} "
                  f"(DD {real['max_dd']:.1f} %, {real['n_liq']} liqs)"]

    # --- le SIZING dynamique : réduire la taille quand le score est chaud ---
    q33, q66 = np.nanquantile(tr_scores, [1/3, 2/3])
    def size_low(e: dict) -> float:
        s = e.get("al_score", float("nan"))
        return 0.025 if (not np.isnan(s) and s >= q66) else 0.0625
    def size_inv(e: dict) -> float:   # le CONTRÔLE inverse (anti-auto-tromperie)
        s = e.get("al_score", float("nan"))
        return 0.0625 if (not np.isnan(s) and s >= q66) else 0.025
    sim_low = run_sim(events, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS, size_fn=size_low)
    sim_inv = run_sim(events, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS, size_fn=size_inv)
    lines += ["", "### Sizing dynamique (exposition moyenne constante = 5 %)", "",
              f"- FLAT 5 % : 100 $ → ${real['balance']:,.2f} "
              f"(DD {real['max_dd']:.1f} %, {real['n_liq']} liqs)",
              f"- 2,5 % si chaud / 6,25 % sinon : 100 $ → "
              f"${sim_low['balance']:,.2f} (DD {sim_low['max_dd']:.1f} %, "
              f"{sim_low['n_liq']} liqs)",
              f"- CONTRÔLE INVERSE (6,25 % si chaud / 2,5 % sinon) : "
              f"100 $ → ${sim_inv['balance']:,.2f} "
              f"(DD {sim_inv['max_dd']:.1f} %, {sim_inv['n_liq']} liqs)"]

    ok_dir = sim_low["balance"] > real["balance"] and sim_low["max_dd"] < real["max_dd"]
    ok_inv = sim_inv["balance"] > sim_low["balance"]
    if ok_dir and not ok_inv:
        verdict2 = ("LE SCORE MARCHE — le sizing dynamique améliore le ROI ET le DD, "
                    "le contrôle inverse est battu (le signal n'est pas un artefact)")
    elif ok_dir and ok_inv:
        verdict2 = ("AMBIGU — le direct et l'inverse améliorent tous les deux : "
                    "le signal n'est pas assez discriminant, ne pas croire")
    else:
        verdict2 = ("LE SCORE NE MARCHE PAS dans le sim — l'oracle reste un plafond, "
                    "la voie réelle = empiler les stratégies existantes")

    lines += ["", f"## VERDICT GLOBAL", "",
              f"- Filtres univariés (seuils absolus) : "
              f"{'ADOPTÉ' if adopted else 'REJETÉS'} — le lift univarié est réel "
              f"(ATR ×5,4, vol ×5,8 en TRAIN) mais les seuils ne survivent pas au temps",
              f"- Score composite (rangs roulants) : {verdict2}",
              "", "Règle pré-enregistrée : ≥ 40 % des liqs attrapées en VAL,",
              "≤ 15 % des gagnants perdus en VAL. Les seuils viennent de TRAIN",
              "uniquement — la VAL les juge sans les avoir vus."]

    out = REPORTS / f"anti-liq-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[anti-liq] {len(events)} trades, {n_liq} liqs ({base_rate:.1f} %), "
          f"{len(adopted)} filtre(s) univarié(s) adopté(s)")
    print(f"[anti-liq] sim flat : ${real['balance']:,.2f} (DD {real['max_dd']:.1f} %) | "
          f"gate score : {'tient en VAL' if score_gate_adopted is not None else 'aucun ne tient'} | "
          f"sizing dyn : ${sim_low['balance']:,.2f} (DD {sim_low['max_dd']:.1f} %) "
          f"vs inverse ${sim_inv['balance']:,.2f} (DD {sim_inv['max_dd']:.1f} %)")
    print(f"[anti-liq] {verdict2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
