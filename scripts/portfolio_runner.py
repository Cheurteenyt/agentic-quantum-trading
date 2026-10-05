#!/usr/bin/env python3
"""LA COUCHE PORTEFEUILLE — Research OS PR-B (rapport v6, brief V3 §176+).

L'étude d'événement dit « l'edge moyen par trade, tous events confondus » ;
elle ne dit RIEN de ce que vit un wallet de 100 $ : chevauchements de
positions, cap de marge, liquidations, mois négatifs, dépendance à la
queue des trades (top 5 % = 1 384 % du pnl sur W42-RECON-1). Cette couche
transforme les events d'une spec en séquence SÉQUENTIELLE de trades —
le test du wallet séquentiel (loi du 25/09 : tout candidat y passe avant
d'entrer dans un stack) :

  - une position par symbole à la fois (anti-chevauchement — le bug ts_ms
    en nanosecondes qui a falsifié toute une génération de sims) ;
  - marge = cap_pct % de l'équité COURANTE par trade, notional = marge × lev ;
  - liquidation ex ante : MAE ≥ 100/lev − 0,5 (la règle 0-liq codifiée) —
    la mort coûte exactement la marge engagée ;
  - funding signé (short reçoit un funding positif, long le paie) ;
  - frais = cost_pct du NOTIONAL (aller-retour) ;
  - bookage au mois de SORTIE (convention du repo) ;
  - DD max sur la courbe d'équité granularité trade.

Baseline anti-dérive (obligatoire au rapport) : equal-weight long-and-hold
1x des MÊMES symboles sur la MÊME vue — si la stratégie ne bat pas le
buy-and-hold de ses propres actifs, l'edge est une narration.

DD par fenêtre gelée : le plafond max_window_loss_pct (15 %) d'active.yaml
s'applique ICI, où un drawdown existe — pas sur des moyennes par trade.

Usage :
    python3 scripts/portfolio_runner.py --id EXP-xxx [--view validation]
    python3 scripts/research_runner.py portfolio --id EXP-xxx   # la même porte

Unités du kernel : ret_H et fund_H en points de %, hi_H/lo_H en FRACTIONS
(converties en % ici). Un wallet sur la vue validation exige un run de
confirmation existant (l'artefact fait foi) — la vue train est libre.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.label_matrix import build_matrix, snapshot_id  # noqa: E402
from scripts.research_os import (  # noqa: E402
    DataScope, load_confirmation_protocol)
from scripts import research_runner as rr  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
RUNS = ROOT / "research" / "runs"
H_MS = 3_600_000


# ------------------------------------------------------------------ events
def collect_events(spec: dict, matrix: dict, feats_by_sym: dict, view,
                   frozen: dict | None = None, min_event_ms: int = 0,
                   db_path: Path = KDB) -> list[dict]:
    """Les events d'une spec sur une vue : la matière du wallet. Chaque
    event porte ce qu'un trade vivrait — ret, MAE, funding, coûts."""
    sig = spec["signal"]
    side = int(sig.get("side", -1))
    cost = float(spec.get("cost_pct", 0.28))
    h1 = int(spec.get("horizons", [24])[0])
    events = []
    n_fund_known = 0
    try:
        from scripts.funding_series import funding_series_for
    except Exception:
        funding_series_for = None
    for sym in spec["data"]["symbols"]:
        if sym not in matrix or sym not in feats_by_sym:
            continue
        cols, feats = matrix[sym], feats_by_sym[sym]
        fz = frozen.get(sym) if frozen is not None else None
        if frozen is not None and fz is None:
            fz = [None] * len(rr._signal_conditions(sig))
        mask = rr.event_mask(spec, feats, view, frozen=fz,
                             min_event_ms=min_event_ms,
                             thr_key=(*rr._db_key(db_path), sym))
        # FIX v10 (audit GLM 5.3 post-#135) : le CALENDRIER réel des prints
        # de funding du symbole — le moteur MTM accrue aux heures EXACTES
        fser = None
        if funding_series_for is not None:
            try:
                fser = funding_series_for(sym, db_path=db_path)
            except Exception:
                fser = None
        ret = cols[f"ret_{h1}"]
        # FIX v8 : la SORTIE (open(i) + H heures) doit rester dans la vue —
        # un trade dont l'horizon déborde simulerait au-delà de la fenêtre
        idx = np.flatnonzero(
            mask & np.isfinite(ret)
            & (feats["open_time_ns"] <= (view.end_ms - h1 * 3_600_000) * 10**6))
        hi = cols[f"hi_{h1}"]
        lo = cols[f"lo_{h1}"]
        fund = cols.get(f"fund_{h1}")
        entry_px = cols["entry"]     # l'open(i) — requis par le moteur MTM
        for i in idx:
            fv = float(fund[i]) if fund is not None else 0.0
            if not np.isfinite(fv):
                fv = 0.0          # l'inconnu contribue 0 ; fund_cov le dit
            else:
                n_fund_known += 1
            # MAE côté position, % : short souffre du high, long du low
            # (hi/lo du kernel sont des FRACTIONS → ×100)
            mae_pct = (float(hi[i]) * 100.0) if side == -1 \
                else (-float(lo[i]) * 100.0)
            t_ms = int(feats["open_time_ns"][i] // 10**6)
            prints = []
            if fser is not None and len(fser.times_ms):
                import numpy as _np
                k0 = int(_np.searchsorted(fser.times_ms, t_ms, side="right"))
                k1 = int(_np.searchsorted(fser.times_ms, t_ms + h1 * 3_600_000,
                                          side="right"))
                signed = 1.0 if side == -1 else -1.0
                prints = [(int(fser.times_ms[k]),
                           float(fser.rates_pct[k]) * signed)
                          for k in range(k0, k1)]
            events.append({
                "sym": sym, "t_ms": t_ms, "exit_ms": t_ms + h1 * 3_600_000,
                "side": side, "ret_pct": float(ret[i]),
                "entry": float(entry_px[i]),
                "mae_pct": mae_pct, "fund_pct": fv, "cost_pct": cost,
                "fund_prints": prints})
    events.sort(key=lambda e: e["t_ms"])
    # FIX v8 (rapport GLM 5.3 №4) : la couverture de funding des events est
    # retournée — l'inconnu ne devient jamais 0 en silence sans être compté
    fund_cov = (n_fund_known / len(events)) if events else 0.0
    return events, fund_cov


# ------------------------------------------------------------------ MTM
def _fetch_marks(db_path: Path, symbols: list[str], start_ms: int,
                 end_ms: int) -> dict[str, dict]:
    """Les marks horaires par symbole : close (MTM réaliste) et high/low
    (borne conservatrice intrabar). Structure {sym: {t, close, high, low}}."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out: dict[str, dict] = {}
    try:
        for sym in symbols:
            rows = con.execute(
                "SELECT open_time, close, high, low FROM klines "
                "WHERE symbol=? AND interval='1h' AND open_time>=? "
                "AND open_time<? ORDER BY open_time",
                (sym, start_ms, end_ms)).fetchall()
            if len(rows) >= 2:
                out[sym] = {"t": np.array([r[0] for r in rows], dtype=np.int64),
                            "close": np.array([float(r[1]) for r in rows]),
                            "high": np.array([float(r[2]) for r in rows]),
                            "low": np.array([float(r[3]) for r in rows])}
    finally:
        con.close()
    return out


def _mark_index(t_arr: np.ndarray, t_ms: int) -> int | None:
    """L'index du DERNIER bar clôturé à l'instant t (open_time < t) —
    aucun look-ahead : le compte est marqué au dernier prix connu."""
    if len(t_arr) == 0 or t_ms <= int(t_arr[0]):
        return None
    return max(int(np.searchsorted(t_arr, t_ms)) - 1, 0)


def _unrealized(pos: dict, marks_map: dict[str, float]) -> float:
    """Le PnL latent d'une position au dernier mark connu (entry si aucun)."""
    px = marks_map.get(pos["sym"], pos["entry"])
    return pos["side"] * (px / pos["entry"] - 1.0) * pos["notional"]


def run_wallet_mtm(events: list[dict], marks: dict[str, dict],
                   capital: float = 100.0, cap_pct: float = 1.0,
                   lev: float = 1.0) -> dict:
    """LE MOTEUR MTM HORAIRE (PR-2, rapport GLM 5.3 №6).

    equity_t = cash + Σ unrealized(position, dernier mark connu) — les
    positions sont marquées CHAQUE HEURE (funding accru heure par heure,
    frais déduits à l'entrée), au lieu d'apparaître seulement à leur
    clôture. Publie :
      - max_dd_mtm       : le DD sur marks CLOSE (ce que le compte a vécu)
      - max_dd_mtm_worst : le DD sur marks intrabar hi/lo (borne haute —
                           l'excursion adverse maximale, short au high,
                           long au low)
      - max_dd_close     : l'ancien DD clôture-seule (comparaison)
    Convention liq inchangée (ex ante, MAE ≥ 100/lev − 0,5, option A) : la
    marge est absorbée ENTIÈREMENT à l'heure d'entrée (frais et funding
    compris — la comptabilité se réconcilie exactement).
    Ordre horaire : sorties → entrées → funding → marks → équité."""
    if not events:
        return run_wallet([], capital=capital, cap_pct=cap_pct, lev=lev)
    evs = sorted(events, key=lambda e: e["t_ms"])
    liq_thr = 100.0 / lev - 0.5
    h1 = (evs[0]["exit_ms"] - evs[0]["t_ms"]) // 3_600_000

    cash = float(capital)
    open_pos: dict[str, dict] = {}
    busy: dict[str, int] = {}
    entries_by_t: dict[int, list[dict]] = {}
    for e in evs:
        entries_by_t.setdefault(e["t_ms"], []).append(e)

    peak = peak_w = peak_c = float(capital)
    max_dd_mtm = max_dd_worst = max_dd_close = 0.0
    liq = wins = skipped = 0
    fees = fund_net = 0.0
    monthly: dict[str, float] = {}
    n_trades = 0
    conc_sum = conc_n = 0
    max_conc = 0
    margin_sum = 0.0
    max_margin_pct = max_gross_pct = 0.0
    max_long_pct = max_short_pct = 0.0
    last_close: dict[str, float] = {}
    last_worst: dict[str, float] = {}

    t = (evs[0]["t_ms"] // H_MS) * H_MS
    t_end = max(e["exit_ms"] for e in evs)
    while t <= t_end:
        # 1. le funding s'accrue AUX HEURES EXACTES des prints réels —
        #    AVANT les sorties : le print de l'heure de sortie est dû
        for pos in open_pos.values():
            while pos["fund_prints"] and pos["fund_prints"][0][0] <= t:
                cash += pos["fund_prints"].pop(0)[1]
        # 2. les sorties réalisent leur PnL (hors funding déjà accru)
        for sym, pos in list(open_pos.items()):
            if pos["exit_ms"] == t:
                realized = (pos["side"] * pos["ret_pct"] / 100.0
                            * pos["notional"])
                cash += realized
                n_trades += 1
                wins += 1 if (realized + pos["fund_total"]
                              - pos["fees"]) > 0 else 0
                month = datetime.fromtimestamp(
                    t / 1000, tz=timezone.utc).strftime("%Y-%m")
                monthly[month] = monthly.get(month, 0.0) + (
                    realized + pos["fund_total"] - pos["fees"])
                fund_net += pos["fund_total"]
                del open_pos[sym]
        # 2. les nouvelles entrées
        for e in entries_by_t.get(t, []):
            if e["sym"] in open_pos:
                skipped += 1
                continue
            eq_now = cash + sum(_unrealized(p, last_close)
                                for p in open_pos.values())
            margin = eq_now * cap_pct / 100.0
            if margin <= 0:
                break
            notional = margin * lev
            month = datetime.fromtimestamp(
                t / 1000, tz=timezone.utc).strftime("%Y-%m")
            if e["mae_pct"] >= liq_thr:
                # option A : la mort absorbe la marge TOUT COMPRIS, dès
                # l'heure d'entrée (le MTM la voit immédiatement)
                cash -= margin
                liq += 1
                n_trades += 1
                monthly[month] = monthly.get(month, 0.0) - margin
                max_dd_mtm = max(max_dd_mtm, 100.0 * margin / eq_now
                                 if eq_now > 0 else 0.0)
                max_dd_worst = max_dd_mtm
            else:
                fee = notional * e["cost_pct"] / 100.0
                cash -= fee
                fees += fee
                fund_signed = e["fund_pct"] * (1.0 if e["side"] == -1 else -1.0)
                # FIX v10 : le chemin RÉEL du funding — les prints aux heures
                # exactes (l'ancien lissage horaire déformait le trajet et
                # donc le DD MTM) ; sans calendrier, accrual au sort
                prints = [(pt, pct * notional / 100.0)
                          for pt, pct in e.get("fund_prints", [])]
                if not prints and e.get("fund_pct"):
                    prints = [(e["exit_ms"], fund_signed * notional / 100.0)]
                open_pos[e["sym"]] = {
                    "sym": e["sym"], "side": e["side"], "entry": e["entry"],
                    "notional": notional, "margin": margin,
                    "ret_pct": e["ret_pct"], "exit_ms": e["exit_ms"],
                    "fees": fee, "fund_total": fund_signed * notional / 100.0,
                    "fund_prints": prints}

        # 4. les marks de l'heure : le DERNIER prix clôturé connu (pas de
        #    look-ahead) ; worst = high intrabar (short) / low (long)
        for sym, pos in open_pos.items():
            mk = marks.get(sym)
            if mk is None:
                continue
            i = _mark_index(mk["t"], t)
            if i is None:
                continue
            last_close[sym] = float(mk["close"][i])
            last_worst[sym] = float(
                (mk["high"] if pos["side"] == -1 else mk["low"])[i])
        # 5. l'équité MTM de l'heure + les métriques de concurrence (№29)
        eq_mtm = cash + sum(_unrealized(p, last_close)
                            for p in open_pos.values())
        eq_worst = cash + sum(_unrealized(p, last_worst)
                              for p in open_pos.values())
        peak = max(peak, eq_mtm)
        max_dd_mtm = max(max_dd_mtm,
                         (peak - eq_mtm) / peak * 100.0 if peak > 0 else 0.0)
        peak_w = max(peak_w, eq_worst)
        max_dd_worst = max(max_dd_worst,
                           (peak_w - eq_worst) / peak_w * 100.0
                           if peak_w > 0 else 0.0)
        peak_c = max(peak_c, cash)
        max_dd_close = max(max_dd_close,
                           (peak_c - cash) / peak_c * 100.0 if peak_c > 0
                           else 0.0)
        conc = len(open_pos)
        conc_sum += conc
        conc_n += 1
        max_conc = max(max_conc, conc)
        if eq_mtm > 0:
            m_used = sum(p["margin"] for p in open_pos.values())
            g_not = sum(p["notional"] for p in open_pos.values())
            mpct = m_used / eq_mtm * 100.0
            margin_sum += mpct
            max_margin_pct = max(max_margin_pct, mpct)
            max_gross_pct = max(max_gross_pct, g_not / eq_mtm * 100.0)
            max_long_pct = max(max_long_pct,
                               sum(p["notional"] for p in open_pos.values()
                                   if p["side"] == 1) / eq_mtm * 100.0)
            max_short_pct = max(max_short_pct,
                                sum(p["notional"] for p in open_pos.values()
                                    if p["side"] == -1) / eq_mtm * 100.0)
        t += H_MS

    months = sorted(monthly)
    final = cash + sum(_unrealized(p, last_close) for p in open_pos.values())
    roi = (final - capital) / capital * 100.0
    return {"capital": capital, "solde": final, "roi_pct": roi,
            "max_dd_pct": max_dd_mtm, "max_dd_mtm": max_dd_mtm,
            "max_dd_mtm_worst": max_dd_worst, "max_dd_close": max_dd_close,
            "liqs": liq, "trades": n_trades,
            "skipped_overlap": skipped,
            "wr_pct": (wins / n_trades * 100.0) if n_trades else 0.0,
            "months_neg": sum(1 for v in monthly.values() if v < 0),
            "months_total": len(months),
            "worst_month": min(monthly.values()) if monthly else 0.0,
            "best_month": max(monthly.values()) if monthly else 0.0,
            "ret_dd": (roi / max_dd_mtm) if max_dd_mtm > 0 else float("inf"),
            "fees": fees, "funding_net": fund_net, "monthly": monthly,
            "max_concurrency": max_conc,
            "avg_concurrency": (conc_sum / conc_n) if conc_n else 0.0,
            "max_margin_used_pct": max_margin_pct,
            "avg_margin_used_pct": (margin_sum / conc_n) if conc_n else 0.0,
            "max_gross_notional_pct": max_gross_pct,
            "max_long_notional_pct": max_long_pct,
            "max_short_notional_pct": max_short_pct,
            "cap_pct": cap_pct, "lev": lev, "mtm": True}


# ------------------------------------------------------------------ wallet
def run_wallet(events: list[dict], capital: float = 100.0,
               cap_pct: float = 1.0, lev: float = 1.0) -> dict:
    """Le wallet séquentiel. Retourne solde, DD, liqs, mois, WR — les
    chiffres qu'un propriétaire vit, pas une moyenne d'events."""
    eq = float(capital)
    peak = eq
    max_dd = 0.0
    busy: dict[str, int] = {}
    liq = wins = 0
    fees = fund_net = 0.0
    monthly: dict[str, float] = {}
    curve: list[tuple[int, float]] = []
    skipped = 0
    liq_thr = 100.0 / lev - 0.5
    # FIX v8 (rapport GLM 5.3 №29) : la concurrence du portefeuille est
    # MESURÉE — le cap 1 %/trade n'empêche pas 10 positions simultanées
    open_exits: list[int] = []
    max_conc = 0
    max_margin_used_pct = 0.0
    for ev in events:
        if ev["t_ms"] < busy.get(ev["sym"], -1):
            skipped += 1
            continue
        # les positions ouvertes dont la sortie est passée libèrent leur marge
        open_exits = [x for x in open_exits if x > ev["t_ms"]]
        margin = eq * cap_pct / 100.0
        if margin <= 0:
            break
        notional = margin * lev
        fund_signed = ev["fund_pct"] * (1.0 if ev["side"] == -1 else -1.0)
        if ev["mae_pct"] >= liq_thr:
            # FIX v8 (rapport GLM 5.3 №28, option A) : la liquidation est une
            # perte TOUT COMPRIS (marge absorbée = prix de liq + frais +
            # funding) — les frais/funding ne sont PAS comptés à côté, la
            # comptabilité se réconcilie exactement : delta_equity = -margin
            pnl = -margin
            liq += 1
        else:
            gross = ev["side"] * ev["ret_pct"] + fund_signed - ev["cost_pct"]
            pnl = notional * gross / 100.0
            fees += notional * ev["cost_pct"] / 100.0
            fund_net += notional * fund_signed / 100.0
        eq += pnl
        wins += 1 if pnl > 0 else 0
        busy[ev["sym"]] = ev["exit_ms"]
        open_exits.append(ev["exit_ms"])
        max_conc = max(max_conc, len(open_exits))
        if eq > 0:
            max_margin_used_pct = max(max_margin_used_pct,
                                      len(open_exits) * cap_pct)
        month = datetime.fromtimestamp(ev["exit_ms"] / 1000,
                                       tz=timezone.utc).strftime("%Y-%m")
        monthly[month] = monthly.get(month, 0.0) + pnl
        curve.append((ev["exit_ms"], eq))
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    n = len(curve)
    months = sorted(monthly)
    months_neg = sum(1 for v in monthly.values() if v < 0)
    worst_m = min(monthly.values()) if monthly else 0.0
    best_m = max(monthly.values()) if monthly else 0.0
    roi = (eq - capital) / capital * 100.0
    return {"capital": capital, "solde": eq, "roi_pct": roi,
            "max_dd_pct": max_dd, "liqs": liq, "trades": n,
            "skipped_overlap": skipped, "wr_pct": (wins / n * 100.0) if n else 0.0,
            "months_neg": months_neg, "months_total": len(months),
            "worst_month": worst_m, "best_month": best_m,
            "ret_dd": (roi / max_dd) if max_dd > 0 else float("inf"),
            "fees": fees, "funding_net": fund_net, "monthly": monthly,
            "max_concurrency": max_conc,
            "max_margin_used_pct": max_margin_used_pct,
            "cap_pct": cap_pct, "lev": lev}


def wallet_per_window(events: list[dict], proto: dict, capital: float,
                      cap_pct: float, lev: float,
                      marks: dict | None = None) -> dict[str, dict]:
    """Le DD du wallet PAR FENÊTRE gelée — là où max_window_loss_pct
    (15 %) s'applique. FIX v10 : même moteur que le global (MTM quand les
    marks sont fournis) — une seule définition du risque dans le rapport."""
    out = {}
    for w in proto.get("frozen_windows", []):
        ws = rr._month_ms(str(w["start"]))
        we = rr._month_ms(str(w["end"]))
        evs = [e for e in events if ws <= e["t_ms"] < we]
        if marks:
            mks = {s: m for s, m in marks.items()
                   if len(m["t"]) and int(m["t"][0]) < we
                   and int(m["t"][-1]) >= ws}
            out[str(w["start"])] = (run_wallet_mtm(evs, mks, capital=capital,
                                                   cap_pct=cap_pct, lev=lev)
                                    if evs and mks else
                                    run_wallet(evs, capital=capital,
                                               cap_pct=cap_pct, lev=lev))
        else:
            out[str(w["start"])] = run_wallet(evs, capital=capital,
                                              cap_pct=cap_pct, lev=lev)
    return out


# ------------------------------------------------------------------ baseline
def baseline_hold(spec: dict, view, db_path: Path = KDB,
                  capital: float = 100.0) -> dict:
    """Equal-weight long-and-hold 1x des symboles de la spec sur la vue —
    le comparateur : si l'edge ne bat pas ses propres actifs tenus passifs,
    il n'y a pas d'edge. Spot 1x long = inliquidable (sauf prix à zéro)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    curves: dict[str, list[tuple[int, float]]] = {}
    try:
        for sym in spec["data"]["symbols"]:
            rows = con.execute(
                "SELECT open_time, close FROM klines WHERE symbol=? "
                "AND interval='1h' AND open_time>=? AND open_time<? "
                "ORDER BY open_time",
                (sym, view.start_ms, view.end_ms)).fetchall()
            if len(rows) < 2:
                continue
            p0 = rows[0][1]
            if not p0:
                continue
            # échantillonnage quotidien (chaque 24e barre) + LA DERNIÈRE —
            # sans elle, le solde final rate la fin réelle de la fenêtre
            pts = [(r[0], r[1] / p0 * capital) for r in rows[::24]]
            if pts[-1][0] != rows[-1][0]:
                pts.append((rows[-1][0], rows[-1][1] / p0 * capital))
            curves[sym] = pts
    finally:
        con.close()
    if not curves:
        return {"solde": float("nan"), "roi_pct": float("nan"),
                "max_dd_pct": float("nan"), "months_neg": 0,
                "per_symbol": {}}
    # la courbe portefeuille = moyenne des courbes normalisées, échantillon
    # commun (intersection des timestamps)
    common = None
    for pts in curves.values():
        ts = {t for t, _ in pts}
        common = ts if common is None else (common & ts)
    times = sorted(common)
    if not times:
        return {"solde": float("nan"), "roi_pct": float("nan"),
                "max_dd_pct": float("nan"), "months_neg": 0,
                "per_symbol": {s: pts[-1][1] for s, pts in curves.items()}}
    maps = {s: dict(pts) for s, pts in curves.items()}
    port = [(t, float(np.mean([m[t] for m in maps.values() if t in m])))
            for t in times]
    peak = capital
    max_dd = 0.0
    for _, eq in port:
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100.0)
    # mois calendaires sur l'équité de fin de mois
    meq: dict[str, float] = {}
    for t, eq in port:
        meq[datetime.fromtimestamp(t / 1000, tz=timezone.utc)
            .strftime("%Y-%m")] = eq
    vals = list(meq.values())
    months_neg = sum(1 for a, b in zip(vals, vals[1:]) if b < a)
    final = port[-1][1]
    return {"solde": final, "roi_pct": (final - capital) / capital * 100.0,
            "max_dd_pct": max_dd, "months_neg": months_neg,
            "months_total": len(meq),
            "per_symbol": {s: pts[-1][1] for s, pts in curves.items()}}


# ------------------------------------------------------------------ run
def _load_frozen(run_id: str) -> tuple[dict | None, str]:
    sfile = RUNS / run_id / "summary_discovery.json"
    if sfile.exists():
        s = json.loads(sfile.read_text(encoding="utf-8"))
        if s.get("frozen_thresholds"):
            return s["frozen_thresholds"], "discovery_artifact"
    return None, "recomputed_train"


def wallet_for_run(run_id: str, db_path: Path = KDB, capital: float = 100.0,
                   cap_pct: float = 1.0, lev: float = 1.0,
                   view_kind: str | None = None,
                   baseline_only: bool = False) -> dict:
    """Le wallet d'un run existant. La vue validation exige un run de
    confirmation (l'artefact summary_confirmation.json fait foi) ; les
    seuils sont ceux de la découverte — JAMAIS re-calibrés."""
    rdir = RUNS / run_id
    spec = json.loads((rdir / "spec.json").read_text(encoding="utf-8"))
    # FIX v8 (rapport GLM 5.3 №15) : on vérifie le VERDICT du résumé de
    # confirmation, pas l'existence du fichier — un run REJECTED ne donne
    # aucun droit à la vue validation.
    conf_verdict = None
    cfile = rdir / "summary_confirmation.json"
    if cfile.exists():
        try:
            conf_verdict = json.loads(
                cfile.read_text(encoding="utf-8")).get("verdict")
        except (OSError, json.JSONDecodeError):
            conf_verdict = None
    vk = view_kind or ("validation" if conf_verdict == "CONFIRMED" else "train")
    if vk == "validation" and conf_verdict != "CONFIRMED":
        raise ValueError(
            f"{run_id} : pas de confirmation CONFIRMED — le wallet "
            "validation se mérite (un slot consommé). Utilisez --view train.")
    d = spec["data"]
    snap = snapshot_id(db_path)
    scope = DataScope(snap, int(d["train_start"]), int(d["train_end"]),
                      int(d["validation_start"]), int(d["validation_end"]))
    use_cache = Path(db_path).resolve() == Path(KDB).resolve()
    _, matrix = build_matrix(d["symbols"],
                             tuple(int(h) for h in spec.get("horizons", [24])),
                             db_path=db_path, use_cache=use_cache)
    proto = load_confirmation_protocol()
    embargo_ms = (int(d["train_end"])
                  + int(proto.get("embargo_hours", 0)) * 3_600_000)
    frozen, frozen_src = (None, "expanding_train") if vk == "train" \
        else _load_frozen(run_id)
    if vk == "validation" and frozen is None:
        train_view = scope.confirmation_view()[0]
        feats0 = rr._features_by_sym(spec, db_path)
        frozen = rr._frozen_thresholds(
            feats0, rr._signal_conditions(spec["signal"]), train_view)
        frozen_src = "recomputed_train"
    if baseline_only:
        view = scope.discovery_view() if vk == "train" \
            else scope.confirmation_view()[1]
        return {"run_id": run_id, "view": vk,
                "baseline": baseline_hold(spec, view, db_path=db_path,
                                          capital=capital)}
    feats_by_sym = rr._features_by_sym(spec, db_path)
    if vk == "train":
        view = scope.discovery_view()
        events, fund_cov = collect_events(spec, matrix, feats_by_sym, view,
                                          frozen=None, min_event_ms=0,
                                          db_path=db_path)
        per_window = None
    else:
        view = scope.confirmation_view()[1]
        events, fund_cov = collect_events(spec, matrix, feats_by_sym, view,
                                          frozen=frozen,
                                          min_event_ms=embargo_ms,
                                          db_path=db_path)
        per_window = wallet_per_window(events, proto, capital, cap_pct, lev,
                                       marks=marks)
    # PR-2 : le moteur MTM horaire quand les marks sont disponibles — le DD
    # published est désormais celui que le compte AURAIT VÉCU heure par heure
    marks = _fetch_marks(db_path, spec["data"]["symbols"],
                         view.start_ms, view.end_ms)
    if marks:
        wallet = run_wallet_mtm(events, marks, capital=capital,
                                cap_pct=cap_pct, lev=lev)
    else:
        wallet = run_wallet(events, capital=capital, cap_pct=cap_pct, lev=lev)
    baseline = baseline_hold(spec, view, db_path=db_path, capital=capital)
    out = {"run_id": run_id, "view": vk, "capital": capital,
           "cap_pct": cap_pct, "lev": lev, "frozen_src": frozen_src,
           "embargo_ms": embargo_ms if vk == "validation" else 0,
           "n_events": len(events), "fund_cov": fund_cov,
           "wallet": wallet, "baseline": baseline,
           "per_window": per_window,
           "max_window_loss_pct": float(proto.get("max_window_loss_pct", 15))}
    if per_window:
        out["window_dd_breach"] = [
            k for k, w in per_window.items()
            if w["max_dd_pct"] > out["max_window_loss_pct"]]
    return out


# ------------------------------------------------------------------ rapport
def wallet_report_block(w: dict) -> str:
    """Le bloc WALLET appendu au report.md d'un run confirmé."""
    wl = w["wallet"]
    bl = w.get("baseline", {})
    lines = ["", "## WALLET (couche portefeuille)", "",
             f"Vue {w['view']} · {wl['capital']:.0f}$ · marge ≤ "
             f"{wl['cap_pct']:.1f} %/trade · lev {wl['lev']:g}x · une "
             "position par symbole · bookage au mois de sortie · seuils "
             f"gelés ({w.get('frozen_src', '?')})", "",
             "| métrique | valeur |", "|---|---|",
             f"| trades pris / events bruts | {wl['trades']} / {w['n_events']} |",
             f"| solde final | ${wl['solde']:.2f} |",
             f"| ROI période | {wl['roi_pct']:+.2f} % |",
             f"| DD max (MTM horaire) | {wl['max_dd_pct']:.2f} % |",
             f"| liquidations | {wl['liqs']} |",
             f"| WR | {wl['wr_pct']:.1f} % |",
             f"| mois négatifs | {wl['months_neg']} / {wl['months_total']} |",
             f"| pire mois / record | {wl['worst_month']:+.2f}$ / "
             f"{wl['best_month']:+.2f}$ |",
             f"| ret/DD | {wl['ret_dd']:.1f} |",
             f"| frais payés | ${wl['fees']:.2f} · funding net "
             f"${wl['funding_net']:+.2f} |"]
    if wl.get("mtm"):
        lines += [
            f"| DD worst intrabar / close-seul | {wl['max_dd_mtm_worst']:.2f} %"
            f" / {wl['max_dd_close']:.2f} % |",
            f"| concurrence max / marge max engagée | "
            f"{wl['max_concurrency']} positions / "
            f"{wl['max_margin_used_pct']:.1f} % de l'équité |"]
    if bl and bl.get("solde") == bl.get("solde"):
        lines.append(
            f"| baseline long-and-hold 1x | ${bl['solde']:.2f} "
            f"(ROI {bl['roi_pct']:+.2f} %, DD {bl['max_dd_pct']:.2f} %) — "
            "l'edge doit BATTRE ça |")
    if w.get("per_window"):
        pw = " · ".join(
            f"{k} {v['max_dd_pct']:.2f} %" for k, v in w["per_window"].items())
        lines.append(f"| DD par fenêtre gelée | {pw} "
                     f"(plafond {w['max_window_loss_pct']:.0f} %) |")
        if w.get("window_dd_breach"):
            lines.append(f"| ⚠️ DÉPASSEMENT plafond DD | "
                         f"{', '.join(w['window_dd_breach'])} |")
    lines.append("")
    return "\n".join(lines)


def cli_portfolio(a) -> int:
    rid = a.id
    w = wallet_for_run(rid, db_path=Path(a.db), capital=a.capital,
                       cap_pct=a.cap_pct, lev=a.lev, view_kind=a.view,
                       baseline_only=a.baseline)
    rdir = RUNS / rid
    rdir.mkdir(parents=True, exist_ok=True)
    if a.baseline:
        bl = w["baseline"]
        print(f"{rid} [baseline {w['view']}] : solde ${bl['solde']:.2f} · "
              f"ROI {bl['roi_pct']:+.2f} % · DD {bl['max_dd_pct']:.2f} % · "
              f"mois nég {bl['months_neg']}")
    else:
        wl = w["wallet"]
        print(f"{rid} [wallet {w['view']}] : ${wl['capital']:.0f} → "
              f"${wl['solde']:.2f} · ROI {wl['roi_pct']:+.2f} % · DD "
              f"{wl['max_dd_pct']:.2f} % · liq {wl['liqs']} · mois nég "
              f"{wl['months_neg']}/{wl['months_total']} · ret/DD "
              f"{wl['ret_dd']:.1f}")
        bl = w.get("baseline", {})
        if bl and bl.get("solde") == bl.get("solde"):
            print(f"  baseline long-and-hold : ${bl['solde']:.2f} "
                  f"(ROI {bl['roi_pct']:+.2f} %)")
        if w.get("window_dd_breach"):
            print(f"  ⚠️ DD fenêtre > plafond {w['max_window_loss_pct']:.0f} % : "
                  f"{', '.join(w['window_dd_breach'])}")
    (rdir / "wallet.json").write_text(
        json.dumps(w, ensure_ascii=False, indent=1, default=float),
        encoding="utf-8")
    if not a.baseline:
        (rdir / "report_wallet.md").write_text(
            wallet_report_block(w), encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--id", required=True)
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--cap-pct", type=float, default=1.0)
    ap.add_argument("--lev", type=float, default=1.0)
    ap.add_argument("--view", choices=["train", "validation"], default=None)
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--db", default=str(KDB))
    return cli_portfolio(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
