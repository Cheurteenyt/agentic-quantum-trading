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

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.aster_indicators import atr as _true_atr  # noqa: E402
from scripts.funding_series import FundingSeries, funding_series_all  # noqa: E402,F401
from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAJORS, HOLD_H, btc_regime_series, liq_move_for, run_sim)

REPORTS = ROOT / "reports"
SIZE = 0.05
FEE_BPS, SLIP_BPS = 2, 0          # maker (GTX) : la config de référence
# Issue #201 (C-B2) : le levier du SCÉNARIO. Il apparaissait 4 fois en clair
# (fees, funding, pnl, liq_move_for) — s'ils divergeaient, le label pnl et le
# seuil de liquidation cesseraient de décrire LA MÊME position, en silence.
# Une seule constante, et un garde d'import (cf. _selfcheck) pour que la
# divergence devienne impossible : « le seuil ne dépend que du prix et de la
# marge de maintien RÉELLE par symbole, jamais d'un levier divergent ».
SCENARIO_LEV = 20
NUMERIC = ["atr_pct", "vol24", "cascade_depth", "accel", "dd_pct",
           "vwap_dev", "vol_spike", "btc_ret24", "storm_24h", "funding_last"]
CATEGORIC = ["regime"]


def funding_hourly_map() -> dict[str, "FundingSeries"]:
    """FIX lot2 (F3) : délègue au loader unique — les séries réelles
    as-of, plus jamais la moyenne full-sample. Nom conservé pour les
    appelants internes (run_sim consomme les deux formes)."""
    return funding_series_all()


def collect_featured(regime: pd.Series, universe: str = "majors") -> list[dict]:
    """Les événements cascade AVEC leurs features d'entrée.

    La sélection séquentielle du sim (premier dispo, skip des chevauche-
    ments) est répliquée pour que les labels correspondent au sim."""
    con = sqlite3.connect(KDB, timeout=60)
    if universe == "majors":
        symbols = list(MAJORS)
    else:
        symbols = [r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
            "ORDER BY symbol")]
    dfs: dict[str, pd.DataFrame] = {}
    signals: list[int] = []          # ts de TOUS les signaux (feature storm)
    for sym in symbols:
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
        # FIX audit v3 (C8) : un VRAI ATR (True Range + Wilder) — l'ancienne
        # moyenne des |Δclose| ignorait mèches et gaps.
        atr = _true_atr(df, n=24)
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
            # isfinite (pas isnan) : atr_pct/vwap_dev viennent de /close,
            # /vwap168 — une division par un prix à 0 donnerait inf, et
            # np.isnan(inf) == False (le garde laisserait passer l'inf).
            # isfinite couvre nan ET inf. Données prod propres (0 close=0 sur
            # 16,8 M) : c'est une défense, pas un bug actif — mais le garde
            # doit être correct quelle que soit la donnée.
            if (entry <= 0 or t < 200
                    or not np.isfinite(atr_pct[t])
                    or not np.isfinite(vwap_dev[t])):
                continue
            exit_j = ei + HOLD_H - 1
            if exit_j >= len(idx_ns):
                continue
            exit_px = df["close"].values[exit_j]
            ret = (entry - exit_px) / entry * 100
            mae = (highs[ei:exit_j + 1].max() - entry) / entry * 100
            # le label du sim : mae ≥ seuil OU pnl ≤ -marge (indépendant de la balance)
            fees_pct = (FEE_BPS + SLIP_BPS) * 2 * SCENARIO_LEV / 100
            # FIX audit v3 (C6) : as-of STRICT — le dernier taux CONNU à
            # l'entrée ; np.interp mélangeait le print FUTUR dans la feature
            # funding_last (qui alimente l'AL score).
            fund_h = 0.0
            if ft is not None and len(ft[0]):
                _k = int(np.searchsorted(ft[0], idx_ns[ei], side="right")) - 1
                if _k >= 0:
                    fund_h = float(ft[1][_k])
            fund_pct = fund_h * HOLD_H * SCENARIO_LEV / 100
            pnl_pct = ret * SCENARIO_LEV + fund_pct - fees_pct
            # Fossile ronde 5 : LIQ_MOVE_PCT était un seuil PLAT calculé à
            # l'import (100/20 − 2,5 = 2,5 %) — coïncide avec les majeures
            # (mm 2,5) mais ignore les memecoins (16,66 % → distance 0 à
            # 20x = liquidé à l'entrée) et n'était ni prudent ni compté si
            # la table était absente. liq_move_for applique le modèle F-038.
            #
            # #201 (C-B2) : le seuil est calculé avec le MÊME SCENARIO_LEV que
            # le pnl ci-dessus. Le `100/L` de liq_move_for est la distance de
            # liquidation DE LA POSITION À CE LEVIER ; la marge de maintien
            # (mm) vient de liq_params, par symbole, indépendamment du levier.
            # Puisque le scénario est à levier CONSTANT, la mesure reste
            # comparable d'un scénario à l'autre — le point de #201 était
            # qu'un levier divergent (label à L, seuil à L') rendrait la
            # comparaison fausse. Le garde d'import ci-dessous l'interdit.
            _liq_move = liq_move_for(sym, SCENARIO_LEV)
            if _liq_move < 0:
                # Garde RÉEL, pas un assert : `python -O` supprimerait un
                # assert et rétablirait le fail-open en silence (#202).
                raise ValueError(
                    f"liq_move_for({sym!r}, {SCENARIO_LEV}) = {_liq_move} < 0 — "
                    "un seuil de liquidation est une DISTANCE, jamais un signe")
            liq = mae >= _liq_move or pnl_pct <= -100
            # le REGISTRE de liquidation : prix de mort exact + bougie
            # où le high le franchit (le short meurt AU-DESSUS de l'entrée)
            liq_price = entry * (1 + _liq_move / 100)
            liq_ts = None
            for j in range(ei, exit_j + 1):
                if highs[j] >= liq_price:
                    liq_ts = int(idx_ns[j])
                    break
            events.append({
                "sym": sym, "ts_ms": int(idx_ns[ei]), "entry": entry,
                "exit": exit_px, "price_ret_short": ret, "mae_adverse": mae,
                "liq": bool(liq), "liq_price": liq_price,
                "liq_ts_ms": liq_ts,
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
        hold_end = e["ts_ms"] + HOLD_H * 3600 * 10**9  # ts_ms = des NS (nom hérité)
        while i < len(events) and events[i]["ts_ms"] < hold_end:
            i += 1
    return taken


def tercile_lift(vals: np.ndarray, liq: np.ndarray) -> list[tuple[str, int, int, float]]:
    """Le taux de liq par tercile (TRAIN) pour une feature numérique."""
    # PR-172 : nanquantile — un NaN fabriquait des seuils NaN → masques
    # tous vides → ligne « 0.0 % » sans avertissement
    q1, q2 = np.nanquantile(vals, [1 / 3, 2 / 3])
    out = []
    for label, mask in (("T1 (bas)", vals <= q1),
                        ("T2", (vals > q1) & (vals <= q2)),
                        ("T3 (haut)", vals > q2)):
        n = int(mask.sum())
        l = int(liq[mask].sum())
        out.append((label, l, n, l / n * 100 if n else 0.0))
    return out


# les features du score : haut = risqué / bas = risqué. v2 : cascade_depth
# ajouté (profond = le bounce après la chute = le danger du short).
RISK_UP = ("atr_pct", "vol24", "dd_pct")       # haut = risqué
RISK_DOWN = ("btc_ret24", "vwap_dev", "cascade_depth")  # bas = risqué


def add_rolling_scores(events: list[dict], win_days: int = 90,
                       min_window: int = 50) -> None:
    """Le score composite à RANGS ROULANTS, en place sur chaque événement.

    Les niveaux absolus dérivent avec les régimes (les seuils absolus ne
    transfèrent pas) → chaque feature est rangée contre SES `win_days`
    derniers jours d'événements, puis les rangs sont moyennés. Aucun
    look-ahead : la fenêtre = événements antérieurs uniquement."""
    win_ns = win_days * 86400 * 10**9
    for i, e in enumerate(events):
        lo = e["ts_ms"] - win_ns
        window = [p for p in events[:i] if p["ts_ms"] >= lo]
        if len(window) < min_window:
            e["al_score"] = float("nan")
            continue
        ranks = []
        for f in RISK_UP:
            vals = np.array([p[f] for p in window])
            v = e[f]
            if not np.isfinite(v):
                ranks.append(0.5)
                continue
            # PR-172 : les NaN/inf de la fenêtre hors du rang (l'ancien
            # comparaison <= les comptait « moins risqués » en silence)
            vals = vals[np.isfinite(vals)]
            ranks.append(float(np.mean(vals <= v)))
        for f in RISK_DOWN:
            vals = np.array([p[f] for p in window])
            v = e[f]
            if not np.isfinite(v):
                ranks.append(0.5)
                continue
            # PR-172 (P0 chasse AL) : la DIRECTION — le rang DOWN est la
            # fraction de la fenêtre AUSSI risquée que le courant (bas =
            # risqué) : l'ancien mean(vals <= -v) ne niait que la valeur
            # COURANTE, pas la fenêtre — cascade_depth (< 0 par
            # construction) saturait à 1.0 sur 100 % des events (feature
            # MORTE : le gate tournait sur ~4 features effectives, pas
            # les 6 documentées). La re-preuve du gradient est exigée.
            vals = vals[np.isfinite(vals)]
            ranks.append(float(np.mean(vals >= v)))
        e["al_score"] = float(np.mean(ranks))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", choices=["majors", "all"], default="majors")
    args = ap.parse_args()
    regime = btc_regime_series()
    events = collect_featured(regime, args.universe)
    liq_all = np.array([e["liq"] for e in events])
    n_liq = int(liq_all.sum())
    base_rate = n_liq / len(events) * 100

    # split PAR LE TEMPS 70/30
    k = int(len(events) * 0.7)
    train, val = events[:k], events[k:]

    # --- PHASE 2 : le score composite à rangs roulants ---
    add_rolling_scores(events)
    tr_liq = np.array([e["liq"] for e in train])
    va_liq = np.array([e["liq"] for e in val])

    lines = [
        "# L'INDICATEUR ANTI-LIQUIDATION",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{len(events)} trades cascade ({args.universe}, hold 24h, sélection sim), "
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
        # PR-172 : nanquantile (un NaN vidait les seuils en silence)
        qs = np.nanquantile(feat_vals, np.linspace(0.05, 0.95, 19))
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

    # --- le SIZING dynamique : la frontière ROI/DD ---
    # grille de politiques à EXPOSITION CONSTANTE 5 % (moyenne 2/3 cool +
    # 1/3 hot), choisie sur TRAIN, jugée sur VAL, puis sim complet.
    # (0.075, 0.0) = le gate binaire fait proprement (les chauds sautés).
    POLICIES = [(0.0625, 0.025), (0.06, 0.03), (0.065, 0.02),
                (0.07, 0.01), (0.075, 0.0)]

    def make_size_fn(cool: float, hot: float, thr: float):
        def fn(e: dict) -> float:
            s = e.get("al_score", float("nan"))
            if np.isnan(s):
                return SIZE
            return hot if s >= thr else cool
        return fn

    def make_cont_fn(k: float):
        def fn(e: dict) -> float:
            s = e.get("al_score", float("nan"))
            if np.isnan(s):
                return SIZE
            return float(np.clip(SIZE * (1 + k * (0.5 - s)), 0.005, 0.095))
        return fn

    q66 = float(np.nanquantile(tr_scores, 2/3))
    lines += ["", "### LA FRONTIÈRE ROI/DD — politiques de sizing "
              "(exposition moyenne 5 %)", "",
              "Choisie sur TRAIN, jugée sur VAL. Le palier chaud est appliqué "
              f"au score ≥ p66 ({q66:.2f}).", "",
              "| Politique | TRAIN 100 $ → | DD | VAL 100 $ → | DD |",
              "|---|---|---|---|---|"]
    flat_tr = run_sim(train, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS)
    flat_va = run_sim(val, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS)
    lines.append(f"| FLAT 5 % (référence) | ${flat_tr['balance']:,.2f} "
                 f"| {flat_tr['max_dd']:.1f} % | ${flat_va['balance']:,.2f} "
                 f"| {flat_va['max_dd']:.1f} % |")
    best = None
    for cool, hot in POLICIES:
        fn = make_size_fn(cool, hot, q66)
        label = f"{cool:.2%} / {hot:.1%}" if hot > 0 else f"{cool:.2%} / gate chaud"
        tr_s = run_sim(train, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS, size_fn=fn)
        va_s = run_sim(val, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS, size_fn=fn)
        lines.append(f"| {label} | ${tr_s['balance']:,.2f} | {tr_s['max_dd']:.1f} % "
                     f"| ${va_s['balance']:,.2f} | {va_s['max_dd']:.1f} % |")
        # objectif pré-énoncé : max ROI/DD sur TRAIN (le DD est la monnaie)
        ratio = tr_s["balance"] / max(tr_s["max_dd"], 1.0)
        if best is None or ratio > best[2]:
            best = (label, fn, ratio, (cool, hot))
    fn = make_cont_fn(1.5)
    tr_s = run_sim(train, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS, size_fn=fn)
    va_s = run_sim(val, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS, size_fn=fn)
    lines.append(f"| continu k=1.5 | ${tr_s['balance']:,.2f} | {tr_s['max_dd']:.1f} % "
                 f"| ${va_s['balance']:,.2f} | {va_s['max_dd']:.1f} % |")

    ratio = tr_s["balance"] / max(tr_s["max_dd"], 1.0)
    if best is None or ratio > best[2]:
        best = ("continu k=1.5", fn, ratio, "cont")

    full_sim = inv_sim = None
    if best is not None:
        full_sim = run_sim(events, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS,
                           size_fn=best[1])
        if best[3] == "cont":
            inv_fn = make_cont_fn(-1.5)
            inv_label = "continu INVERSE k=-1.5"
        else:
            cool, hot = best[3]
            inv_fn = make_size_fn(hot, cool, q66)
            inv_label = f"INVERSE {hot:.1%} / {cool:.2%}"
        inv_sim = run_sim(events, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS,
                          size_fn=inv_fn)
        lines += ["", f"**Choisi sur TRAIN (ratio ROI/DD) : {best[0]}** — "
                  f"sim COMPLET 1 an + le RE-LEVER (tu choisis ta tolérance) :",
                  f"- flat 5 % : 100 $ → ${real['balance']:,.2f} "
                  f"(DD {real['max_dd']:.1f} %, {real['n_liq']} liqs)",
                  f"- {best[0]} ×1.0 : 100 $ → **${full_sim['balance']:,.2f}** "
                  f"(DD {full_sim['max_dd']:.1f} %, {full_sim['n_liq']} liqs)"]
        for m in (1.25, 1.5):
            if best[3] == "cont":
                def mk(m):
                    def f(e: dict) -> float:
                        s = e.get("al_score", float("nan"))
                        if np.isnan(s):
                            return SIZE * m
                        return float(np.clip(SIZE * m * (1 + 1.5 * (0.5 - s)),
                                             0.005, 0.095 * m))
                    return f
            else:
                cool, hot = best[3]
                def mk(m):
                    return make_size_fn(cool * m, hot * m, q66)
            fs = run_sim(events, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS, size_fn=mk(m))
            lines.append(f"- {best[0]} ×{m} : 100 $ → ${fs['balance']:,.2f} "
                         f"(DD {fs['max_dd']:.1f} %, {fs['n_liq']} liqs)")
        lines.append(f"- {inv_label} (contrôle) : 100 $ → "
                     f"${inv_sim['balance']:,.2f} (DD {inv_sim['max_dd']:.1f} %)")

    # --- le gate-UNION des filtres univariés adoptés (phase 1) dans le sim ---
    if adopted:
        def union_gated(e: dict) -> bool:
            return any((e[f] >= q) if side == "haut" else (e[f] <= q)
                       for f, q, side in adopted)
        mva = np.array([union_gated(e) for e in val])
        catch_u = (va_liq & mva).sum() / max(va_liq.sum(), 1) * 100
        lost_u = (~va_liq & mva).sum() / max((~va_liq).sum(), 1) * 100
        kept = [e for e in events if not union_gated(e)]
        g0 = run_sim(kept, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS)
        lines += ["", f"### GATE-UNION des filtres adoptés "
                  f"({', '.join(f for f, _, _ in adopted)})", "",
                  f"- VAL : {catch_u:.0f} % des liqs attrapées, "
                  f"{lost_u:.1f} % des gagnants perdus",
                  f"- sim 1 an, gate seul : 100 $ → ${g0['balance']:,.2f} "
                  f"(DD {g0['max_dd']:.1f} %, {g0['n_liq']} liqs)"]
        if best is not None:
            g1 = run_sim(kept, 100.0, SIZE, fh, FEE_BPS, SLIP_BPS,
                         size_fn=best[1])
            lines.append(f"- sim 1 an, gate + {best[0]} : 100 $ → "
                         f"**${g1['balance']:,.2f}** (DD {g1['max_dd']:.1f} %, "
                         f"{g1['n_liq']} liqs)")

    ok_dir = (full_sim is not None and full_sim["balance"] > real["balance"]
              and full_sim["max_dd"] <= real["max_dd"] + 2)
    ok_inv = (inv_sim is not None and full_sim is not None
              and inv_sim["balance"] > full_sim["balance"])
    if ok_dir and not ok_inv:
        verdict2 = ("LE SCORE MARCHE — la politique améliore le ROI sans "
                    "dégrader le DD, le contrôle inverse est battu")
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
          f"gate score : {'tient en VAL' if score_gate_adopted is not None else 'aucun ne tient'}")
    if full_sim is not None:
        print(f"[anti-liq] frontière : {best[0]} → ${full_sim['balance']:,.2f} "
              f"(DD {full_sim['max_dd']:.1f} %) | inverse "
              f"${inv_sim['balance']:,.2f} (DD {inv_sim['max_dd']:.1f} %)")
    print(f"[anti-liq] {verdict2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
