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
from scripts.portfolio_sim import liq_move_for  # noqa: E402
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
        # FIX v16 (PR-149, audit GLM 5.3 №1) : l'univers est une obligation
        # INTERNE du chemin wallet — le DD du gate doit être calculé sur la
        # MÊME population d'events que la statistique de confirmation
        mask = rr.apply_universe(spec, sym, mask, feats, h1)
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


HOURS_PER_YEAR = 24.0 * 365.25


def _portfolio_time_metrics(equity_hourly: list[tuple[int, float]]
                            ) -> tuple[float | None, float | None]:
    """Les métriques PORTFEUILLE : rendements heure par heure sur la courbe
    MTM — Sharpe = mean/sd × √(heures/an), Sortino idem en downside. C'est
    la vraie unité d'observation (l'ancien « Sortino » était un artefact de
    fréquence de trades : 79,7)."""
    if len(equity_hourly) < 3:
        return None, None
    eqs = np.array([e for _, e in equity_hourly])
    prev = eqs[:-1]
    cur = eqs[1:]
    ok = prev > 0
    if ok.sum() < 2:
        return None, None
    r = (cur[ok] / prev[ok] - 1.0)
    sd = float(np.std(r, ddof=1))
    mean_r = float(np.mean(r))
    if sd <= 0:
        return None, None
    sharpe = mean_r / sd * np.sqrt(HOURS_PER_YEAR)
    downside = float(np.sqrt(np.mean(np.minimum(r, 0.0) ** 2)))
    sortino = (mean_r / downside * np.sqrt(HOURS_PER_YEAR)
               if downside > 0 else None)
    return round(sharpe, 2), (round(sortino, 2) if sortino else None)


def _unrealized(pos: dict, marks_map: dict[str, float]) -> float:
    """Le PnL latent d'une position au dernier mark connu (entry si aucun).
    FIX v18 (PR-150 №3) : un symbole SANS mark est une COUVERTURE DE RISQUE
    incomplète — le wallet publie mark_coverage_pct et le chemin officiel
    est fail-closed (voir wallet_for_run)."""
    px = marks_map.get(pos["sym"], pos["entry"])
    return pos["side"] * (px / pos["entry"] - 1.0) * pos["notional"]


def run_wallet_mtm(events: list[dict], marks: dict[str, dict],
                   capital: float = 100.0, cap_pct: float = 1.0,
                   lev: float = 1.0,
                   span: tuple[int, int] | None = None,
                   liq_mode: str = "simulated") -> dict:
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
    Convention liq (option A : la mort absorbe la marge TOUT COMPRIS —
    la comptabilité se réconcilie exactement) avec DEUX timings :
      - liq_mode="simulated" (défaut, PR-8) : la position vit heure par
        heure et meurt au PREMIER franchissement du seuil (100/lev − 0,5)
        sur le chemin intrabar réel — la trajectoire d'exécution ;
      - liq_mode="stress" (l'ancienne) : la marge est absorbée ENTIÈREMENT
        dès l'heure d'entrée — la borne conservatrice (le moteur sait ex
        ante, via la MAE de l'horizon, que le trade mourra).
    Ordre horaire : sorties → entrées → funding → marks → équité."""
    if not events:
        return run_wallet([], capital=capital, cap_pct=cap_pct, lev=lev)
    evs = sorted(events, key=lambda e: e["t_ms"])
    # FIX F-038 — la borne est par SYMBOLE (maintMarginPercent réel), plus
    # un seul seuil wallet. Les 6 majeures sont à 2,5 %, pas 0,5 % : le
    # seuil dur repoussait la ligne de mort de 2 points (à 20x) et
    # sous-comptait les liquidations.
    def _thr(sym: str) -> float:
        return liq_move_for(sym, lev)

    h1 = (evs[0]["exit_ms"] - evs[0]["t_ms"]) // 3_600_000

    cash = float(capital)
    open_pos: dict[str, dict] = {}
    open_flux: set[str] = set()   # PR-169 : les slots FLUX ouverts
    busy: dict[str, int] = {}     # PR-169 : désormais LU (fin réelle par slot)
    entries_by_t: dict[int, list[dict]] = {}
    for e in evs:
        entries_by_t.setdefault(e["t_ms"], []).append(e)

    peak = peak_w = peak_c = float(capital)
    max_dd_mtm = max_dd_worst = max_dd_close = 0.0
    liq = wins = skipped = 0
    fees = fund_net = 0.0
    monthly: dict[str, float] = {}
    trade_pnls: list[dict] = []
    n_trades = 0
    conc_sum = conc_n = 0
    max_conc = 0
    margin_sum = 0.0
    equity_hourly: list[tuple[int, float]] = []
    max_margin_pct = max_gross_pct = 0.0
    max_long_pct = max_short_pct = 0.0
    last_close: dict[str, float] = {}
    last_worst: dict[str, float] = {}
    stale_mark_hours = 0
    max_mark_gap_h = 0

    # FIX v19 (№16) : la timeline démarre au span[0] de la VUE (pas du
    # premier trade) — les heures plates avant le premier trade sont
    # représentées à equity = capital
    if span:
        t = (span[0] // H_MS) * H_MS
        t_end = max(span[1], max(e["exit_ms"] for e in evs))
    else:
        t = (evs[0]["t_ms"] // H_MS) * H_MS
        t_end = max(e["exit_ms"] for e in evs)
    while t <= t_end:
        # 1. le funding s'accrue AUX HEURES EXACTES des prints réels —
        #    AVANT les sorties : le print de l'heure de sortie est dû
        for pos in open_pos.values():
            # PR-167 (P2) : les prints à HH:00:00.002 (jitter DB) sont
            # accrûs à LEUR heure — l'ancien <= t sur la grille glissait
            # chaque print jitteré d'une heure (montants justes, chemin
            # de DD décalé)
            while pos["fund_prints"] and (
                    (pos["fund_prints"][0][0] // H_MS) * H_MS) <= t:
                amt = pos["fund_prints"].pop(0)[1]
                cash += amt
                pos["fund_accrued"] = pos.get("fund_accrued", 0.0) + amt
        # 2. les sorties réalisent leur PnL (hors funding déjà accru) ;
        #    un liq_pending qui atteint sa sortie sans franchissement
        #    détecté (donnée trouée) est absorbé à la sortie (option A)
        for sym, pos in list(open_pos.items()):
            if pos["exit_ms"] == t:
                n_trades += 1
                month = datetime.fromtimestamp(
                    t / 1000, tz=timezone.utc).strftime("%Y-%m")
                # PR-167 (P1 couche argent) : la liq intrabar de la BOUGIE
                # DE SORTIE — l'ancien code réalisait le ret (ici, step 2)
                # AVANT le test de franchissement (step 4) : le hi/lo de
                # la dernière bougie n'était JAMAIS confronté au seuil
                # (preuve : short 10x, high +12 % ≥ seuil 9,5 %, close
                # +1 % → liqs=0 au lieu de 1 ; run_stack comptait la liq
                # → les deux moteurs divergeaient sur le même event)
                mk_x = marks.get(sym)
                crossed = False
                if mk_x is not None and (liq_mode == "simulated"
                                         or pos.get("liq_pending")):
                    i_x = _mark_index(mk_x["t"], t)
                    if i_x is not None:
                        worst_x = float(
                            (mk_x["high"] if pos["side"] == -1
                             else mk_x["low"])[i_x])
                        adverse_x = ((worst_x / pos["entry"] - 1.0)
                                     if pos["side"] == -1
                                     else (1.0 - worst_x / pos["entry"])) * 100.0
                        crossed = adverse_x >= _thr(sym)
                if pos.get("liq_pending") or crossed:
                    cash += -pos["margin"] + pos["fees"] \
                        - pos.get("fund_accrued", 0.0)
                    liq += 1
                    monthly[month] = monthly.get(month, 0.0) - pos["margin"]
                    trade_pnls.append({"sym": sym,
                                       "t_ms": pos["entry_ms"], "exit_ms": t,
                                       "notional": pos["notional"],
                                       "net": -pos["margin"],
                                       "liquidated": True})
                    fund_net += pos.get("fund_accrued", 0.0)
                    # PR-169 : le slot se libère à la FIN RÉELLE (l'heure
                    # de mort) — même sémantique que run_stack
                    open_flux.discard(pos.get("flux", sym))
                    busy[pos.get("flux", sym)] = t
                    del open_pos[sym]
                    continue
                realized = (pos["side"] * pos["ret_pct"] / 100.0
                            * pos["notional"])
                cash += realized
                # PR-167 (P2) : le funding COMPTABILISÉ est celui réellement
                # accrû (prints couverts) — l'ancien fund_total théorique
                # revendiquait un funding que le cash n'a pas reçu
                _fa = pos.get("fund_accrued", 0.0)
                wins += 1 if (realized + _fa - pos["fees"]) > 0 else 0
                net = realized + _fa - pos["fees"]
                monthly[month] = monthly.get(month, 0.0) + net
                trade_pnls.append({"sym": pos["sym"],
                                   "t_ms": pos["entry_ms"], "exit_ms": t,
                                   "notional": pos["notional"], "net": net,
                                   "liquidated": False})
                fund_net += _fa
                # PR-169 : fin réelle = l'heure de sortie ; slot libéré
                open_flux.discard(pos.get("flux", sym))
                busy[pos.get("flux", sym)] = t
                del open_pos[sym]
        # 2. les nouvelles entrées
        for e in entries_by_t.get(t, []):
            # PR-169 (P1 composition) : le slot est LU (l'ancien busy était
            # écrit, jamais consulté — re-entrée 1 h après une liq) et la
            # CLÉ est le FLUX (doctrine run_stack « 1 slot par flux ») —
            # l'ancienne clé symbole laissait un même flux tenir N
            # positions simultanées en forward contre 1 dans la
            # composition mesurée. Frontière inclusive : entrée à
            # exactement la fin réelle = autorisée.
            _key = e.get("strategy") or e["sym"]
            if _key in open_flux or t < busy.get(_key, 0):
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
            if e["mae_pct"] >= _thr(e["sym"]) and liq_mode == "stress":
                # option A, borne conservatrice : la mort absorbée dès
                # l'entrée (le moteur sait ex ante que le trade mourra)
                cash -= margin
                liq += 1
                n_trades += 1
                monthly[month] = monthly.get(month, 0.0) - margin
                # FIX v12 (audit GLM 5.3 post-#138) : une liquidation produit
                # le MÊME objet normalisé que les autres trades — toutes les
                # métriques (PF, top-N, effective-N, bootstrap) la consomment
                trade_pnls.append({"sym": e["sym"], "t_ms": t,
                                   "exit_ms": e["exit_ms"],
                                   "notional": notional, "net": -margin,
                                   "liquidated": True})
                # (mode stress : la position n'a jamais vécu — aucun
                # funding accru, fund_net ne bouge pas)
                max_dd_mtm = max(max_dd_mtm, 100.0 * margin / eq_now
                                 if eq_now > 0 else 0.0)
                # PR-167 (P2) : le mode stress ne doit PAS écraser le
                # pire DD déjà mesuré (l'ancien = rétrogradait l'invariant
                # publié worst ≥ mtm)
                max_dd_worst = max(max_dd_worst, max_dd_mtm)
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
                    "ret_pct": e["ret_pct"], "entry_ms": t,
                    "exit_ms": e["exit_ms"],
                    "fees": fee, "fund_total": fund_signed * notional / 100.0,
                    "fund_prints": prints,
                    # PR-169 : la clé de slot FLUX portée par la position
                    "flux": e.get("strategy") or e["sym"],
                    # FIX v18 (PR-150 №5) : le mode SIMULÉ ne regarde
                    # JAMAIS le MAE futur — la liquidation est décidée
                    # uniquement par les marks observés heure par heure ;
                    # le mode stress garde la borne ex ante (liq_pending)
                    "liq_pending": (e["mae_pct"] >= _thr(e["sym"])
                                    and liq_mode == "stress")}
                open_flux.add(e.get("strategy") or e["sym"])

        # 4. les marks de l'heure : le DERNIER prix clôturé connu (pas de
        #    look-ahead) ; worst = high intrabar (short) / low (long)
        for sym, pos in list(open_pos.items()):
            mk = marks.get(sym)
            if mk is None:
                continue
            i = _mark_index(mk["t"], t)
            if i is None:
                continue
            last_close[sym] = float(mk["close"][i])
            worst_px = float(
                (mk["high"] if pos["side"] == -1 else mk["low"])[i])
            last_worst[sym] = worst_px
            # PR-8 : CONTIGUOUS_MARK — un trou de données rend le mark
            # suspect ; on le publie (le mark lui-même est conservé, la
            # politique « risque UNKNOWN » reste une option future)
            gap_h = (t - int(mk["t"][i])) // H_MS - 1
            if gap_h > 0:
                stale_mark_hours += gap_h
                max_mark_gap_h = max(max_mark_gap_h, gap_h)
            # PR-8 : LIQ_SIMULATED — la mort au PREMIER franchissement réel
            # du seuil sur le chemin intrabar (la position vit jusqu'ici :
            # la trajectoire d'exécution, pas l'oracle ex ante)
            # FIX v14 (audit GLM 5.3 №6) : JAMAIS la bougie pré-entry — le
            # mark connu à l'heure d'entrée précède la position ; le premier
            # test de franchissement se fait à entry + 1h
            if ((liq_mode == "simulated"
                 or pos.get("liq_pending")) and t > pos["entry_ms"]):
                adverse = ((worst_px / pos["entry"] - 1.0)
                           if pos["side"] == -1
                           else (1.0 - worst_px / pos["entry"])) * 100.0
                if adverse >= _thr(pos["sym"]):
                    # total de la position = −marge (option A) : le cash a
                    # déjà payé les frais (−fee à l'entrée) et reçu le
                    # funding (+Σ) → la clôture ramène le cumul exactement
                    # à −marge : X = −marge + fee − funding_accrué
                    cash += -pos["margin"] + pos["fees"] \
                        - pos.get("fund_accrued", 0.0)
                    liq += 1
                    n_trades += 1
                    month = datetime.fromtimestamp(
                        t / 1000, tz=timezone.utc).strftime("%Y-%m")
                    monthly[month] = monthly.get(month, 0.0) - pos["margin"]
                    trade_pnls.append({"sym": sym, "t_ms": pos["entry_ms"],
                                       "exit_ms": t,
                                       "notional": pos["notional"],
                                       "net": -pos["margin"],
                                       "liquidated": True})
                    fund_net += pos.get("fund_accrued", 0.0)
                    del open_pos[sym]
                    # PR-169 : fin réelle = l'heure de mort (l'ancien
                    # exit_ms prévu bloquait le slot au-delà de la mort) ;
                    # busy est désormais consulté à l'entrée
                    busy[pos.get("flux", sym)] = t
                    open_flux.discard(pos.get("flux", sym))
        # 5. l'équité MTM de l'heure + les métriques de concurrence (№29)
        eq_mtm = cash + sum(_unrealized(p, last_close)
                            for p in open_pos.values())
        eq_worst = cash + sum(_unrealized(p, last_worst)
                              for p in open_pos.values())
        equity_hourly.append((t, eq_mtm))
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
    # — PR-6 : les métriques du rapport final (§36) —
    pnl_list = [tp["net"] for tp in trade_pnls]
    wins_gross = sum(x for x in pnl_list if x > 0)
    losses_gross = abs(sum(x for x in pnl_list if x < 0))
    profit_factor = (wins_gross / losses_gross) if losses_gross > 0 \
        else float("inf") if wins_gross > 0 else 0.0
    if span is not None:
        # FIX v12 (audit GLM 5.3 post-#138) : le CAGR mesure la durée de la
        # VUE (premier trade → dernier exit sous-estimait les mois plats)
        years = (span[1] - span[0]) / (365.25 * 86400_000)
    elif trade_pnls:
        years = ((trade_pnls[-1]["exit_ms"] - trade_pnls[0]["t_ms"])
                 / (365.25 * 86400_000))
    else:
        years = 0.0
    cagr = ((final / capital) ** (1.0 / years) - 1.0) * 100.0 \
        if years > 0 and final > 0 else float("nan")
    # le Sortino TRADE-LEVEL (métrique secondaire, nommé honnêtement —
    # l'annualisation par la fréquence de trades gonflait le chiffre :
    # 79,7 « portefeuille » étaient en réalité un artefact de fréquence)
    rets_pct = [tp["net"] / tp["notional"] * 100.0 for tp in trade_pnls]
    downside = float(np.sqrt(np.mean([min(r, 0.0) ** 2 for r in rets_pct])
                             )) if rets_pct else 0.0
    if rets_pct and downside > 0:
        mean_r = float(np.mean(rets_pct))
        per_year = len(rets_pct) / max(years, 1 / 365.25)
        trade_sortino = mean_r / downside * np.sqrt(per_year)
    else:
        trade_sortino = None
    # les métriques PORTFEUILLE sur la courbe d'équité horaire (la vraie
    # unité d'observation — rendements heure par heure)
    p_sharpe, p_sortino = _portfolio_time_metrics(equity_hourly)
    def _solde_sans_top(pct_cut: float) -> float:
        if not pnl_list:
            return final
        k = max(1, int(round(len(pnl_list) * pct_cut / 100.0)))
        worst = sorted(pnl_list, reverse=True)[k:]
        return capital + sum(worst)
    return {"capital": capital, "solde": final, "roi_pct": roi,
            "cagr_pct": cagr, "years": years,
            "portfolio_sharpe": p_sharpe, "portfolio_sortino": p_sortino,
            "trade_sortino": trade_sortino,
            "profit_factor": profit_factor,
            "equity_hourly": equity_hourly,
            "solde_sans_top1": _solde_sans_top(1.0),
            "solde_sans_top5": _solde_sans_top(5.0),
            "solde_sans_top10": _solde_sans_top(10.0),
            "trade_pnls": trade_pnls,
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
            "stale_mark_hours": stale_mark_hours,
            "max_mark_gap_h": max_mark_gap_h,
            "liq_mode": liq_mode,
            "mark_coverage_pct": (
                len({p["sym"] for p in open_pos.values()} |
                    {tp["sym"] for tp in trade_pnls}) /
                max(len({e["sym"] for e in events}), 1) * 100.0)
            if events else 100.0,
            # FIX v19 (№13) : la couverture par les SYMBOLES REQUIS (pas
            # les trades observés — un symbole sans mark mais avec des
            # trades était faussement « couvert »)
            "required_symbols": len({e["sym"] for e in events}),
            "avg_concurrency": (conc_sum / conc_n) if conc_n else 0.0,
            "max_margin_used_pct": max_margin_pct,
            "avg_margin_used_pct": (margin_sum / conc_n) if conc_n else 0.0,
            "max_gross_notional_pct": max_gross_pct,
            "max_long_notional_pct": max_long_pct,
            "max_short_notional_pct": max_short_pct,
            "cap_pct": cap_pct, "lev": lev, "mtm": True}


# ------------------------------------------------------- effective N
def effective_sample_size(trade_pnls: list[dict]) -> dict:
    """PR-6, amélioration 2 du rapport : n = 20 000 events chevauchants ne
    valent pas 20 000 observations indépendantes. Publie n_raw, n_nonoverlap
    (balayage glouton global), autocorr_1 et effective_n (ajustement AR(1))."""
    n_raw = len(trade_pnls)
    if n_raw == 0:
        return {"n_raw": 0, "n_nonoverlap": 0, "autocorr_1": None,
                "effective_n": 0}
    # FIX v12 : l'ordre des trades SIMULTANÉS ne doit pas influencer
    # l'autocorrélation — tri déterministe (t_ms, sym)
    ordered = sorted(trade_pnls, key=lambda x: (x["t_ms"], x.get("sym", "")))
    n_nonoverlap, last_exit = 0, -1
    for tp in ordered:
        if tp["t_ms"] >= last_exit:
            n_nonoverlap += 1
            last_exit = tp["exit_ms"]
    rets = np.array([tp["net"] / tp["notional"] * 100.0
                     for tp in ordered])
    n_buckets = len({tp["t_ms"] // H_MS for tp in trade_pnls})
    rho = None
    if n_raw > 2 and float(np.std(rets)) > 0:
        rho = float(np.corrcoef(rets[:-1], rets[1:])[0, 1])
    if rho is not None and -0.99 < rho < 0.99:
        eff = max(1.0, n_raw * (1.0 - rho) / (1.0 + rho))
    else:
        eff = float(n_raw)
    return {"n_raw": n_raw, "n_nonoverlap": n_nonoverlap,
            "n_time_buckets": n_buckets,
            "autocorr_1": rho, "effective_n": round(eff, 1)}


# ------------------------------------------------------- bootstrap
def block_bootstrap_hourly(hourly_rets: np.ndarray, block_hours: int = 24,
                           iters: int = 2000, seed: int = 42,
                           hours_per_year: float = HOURS_PER_YEAR) -> dict:
    """PR-7 (audit GLM 5.3 post-#138) : le bootstrap par blocs MOVING-BLOCK
    en UNITÉS TEMPORELLES (heures) sur les rendements PORTFEUILLE — l'ancien
    découpage « 8 trades » tranchait arbitrairement la dépendance temporelle
    (des trades simultanés multi-symboles tombaient dans le même bloc).

    Publie (noms honnêtes) :
      - mean_ci95 et sharpe_ci95 : le Sharpe = mean/sd annualisé à l'heure
        (SANS √n — l'ancien « sharpe_trade » multiplié par √n était une
        t-statistique, publiée séparément) ;
      - t_stat_ci95 : mean / (sd/√n) — la significativité ;
      - bootstrap_mass_mean_gt0 : la PART des réplications > 0 (pas une
        probabilité bayésienne) + les comptes n_neg/iters, plus honnêtes
        qu'un « 100 % ».
      - p_stress : la masse bootstrap du stress de coûts ×1,5 (retire
        0,5 × cost_pct du rendement horaire, en % du notional ≈ ×cap).
    """
    r = np.asarray(hourly_rets, dtype=float)
    if len(r) < block_hours:
        return {"iters": 0, "note": "pas assez d'heures pour bootstrapper"}
    rng = np.random.default_rng(seed)
    n = len(r)
    n_blocks = int(np.ceil(n / block_hours))
    starts = rng.integers(0, n - block_hours + 1, size=(iters, n_blocks))
    means = np.empty(iters)
    sharpes = np.empty(iters)
    tstats = np.empty(iters)
    for i in range(iters):
        idx = (starts[i][:, None] + np.arange(block_hours)[None, :]).ravel()[:n]
        sample = r[idx]
        m, sd = float(sample.mean()), float(sample.std(ddof=1))
        means[i] = m
        if sd > 0:
            sharpes[i] = m / sd * np.sqrt(hours_per_year)
            tstats[i] = m / (sd / np.sqrt(n))
        else:
            sharpes[i] = tstats[i] = 0.0
    n_neg = int((means <= 0).sum())
    return {"iters": iters, "block_hours": block_hours, "seed": seed,
            "mean_ci95": [float(np.percentile(means, 2.5)),
                          float(np.percentile(means, 97.5))],
            "sharpe_ci95": [float(np.percentile(sharpes, 2.5)),
                            float(np.percentile(sharpes, 97.5))],
            "t_stat_ci95": [float(np.percentile(tstats, 2.5)),
                            float(np.percentile(tstats, 97.5))],
            "bootstrap_mass_mean_gt0": float((means > 0).mean()),
            "n_neg_mean": n_neg,
            "n_replications": iters}


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
    # FIX v8 (rapport GLM 5.3 №29) : la concurrence du portefeuille est
    # MESURÉE — le cap 1 %/trade n'empêche pas 10 positions simultanées
    open_exits: list[int] = []
    max_conc = 0
    max_margin_used_pct = 0.0
    for ev in events:
        if ev["t_ms"] < busy.get(ev["sym"], -1):
            skipped += 1
            continue
        # DÉFENSE (bug trouvé par fuzz 2026-10-10) : un event rechargé d'un
        # fichier JSON (écrit à la main, ou corrompu par une division amont)
        # peut porter un ret_pct/fund_pct/cost_pct = NaN ou inf. Sans garde,
        # il entre dans `gross` puis `eq` (solde) et CORROMPT EN SILENCE tout
        # ce qui suit : la courbe, les mois, le DD, le ROI final — un chiffre
        # faux qui a l'air d'un chiffre. La garde isfinite existe EN AMONT
        # (génération d'events) mais pas ici : un event qui bypass cette
        # étape n'est plus protégé. Fail-closed : on skppe l'event pourri et
        # on le COMPTE (skipped) pour qu'il se voie.
        _pourri = any(
            not isinstance(ev.get(k), (int, float))
            or not np.isfinite(ev[k])
            for k in ("ret_pct", "fund_pct", "cost_pct")
        )
        if _pourri:
            skipped += 1
            continue
        # les positions ouvertes dont la sortie est passée libèrent leur marge
        open_exits = [x for x in open_exits if x > ev["t_ms"]]
        margin = eq * cap_pct / 100.0
        if margin <= 0:
            break
        notional = margin * lev
        fund_signed = ev["fund_pct"] * (1.0 if ev["side"] == -1 else -1.0)
        if ev["mae_pct"] >= liq_move_for(ev["sym"], lev):
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
            # FIX v19 (PR-155 №12) : marks PARTIELS pour une fenêtre =
            # DD_UNKNOWN (le fallback close-only n'est plus silencieux)
            ev_syms = {e["sym"] for e in evs}
            mk_syms = {s for s in ev_syms if s in mks and len(mks[s]["t"]) >= 2}
            if ev_syms and mk_syms < ev_syms:
                # des events sur des symboles sans marks suffisants
                out[str(w["start"])] = run_wallet(
                    evs, capital=capital, cap_pct=cap_pct, lev=lev)
                out[str(w["start"])]["dd_status"] = "UNKNOWN"
                out[str(w["start"])]["max_dd_pct"] = float("nan")
            else:
                out[str(w["start"])] = (run_wallet_mtm(evs, mks, capital=capital,
                                                       cap_pct=cap_pct, lev=lev)
                                        if evs and mks else
                                        run_wallet(evs, capital=capital,
                                                   cap_pct=cap_pct, lev=lev))
                out[str(w["start"])]["dd_status"] = "MTM"
        else:
            out[str(w["start"])] = run_wallet(evs, capital=capital,
                                              cap_pct=cap_pct, lev=lev)
            out[str(w["start"])]["dd_status"] = "CLOSE_ONLY"
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
    # FIX v12 (audit GLM 5.3) : le PREMIER mois se compare au capital
    # initial — l'ancien zip(vals, vals[1:]) le rates
    months_neg = (1 if vals and vals[0] < capital else 0) \
        + sum(1 for a, b in zip(vals, vals[1:]) if b < a)
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
    # les marks horaires du span — le moteur MTM marque le compte heure
    # par heure (le DD publié est celui que le compte AURAIT VÉCU)
    marks = _fetch_marks(db_path, spec["data"]["symbols"],
                         view.start_ms, view.end_ms)
    # FIX v18 (PR-150 №3) : FAIL-CLOSED sur les marks partiels — un
    # symbole sans mark serait valorisé à son entrée (un DD
    # artificiellement faible) ; le chemin officiel exige 100 %
    missing = [s for s in spec["data"]["symbols"] if s not in marks]
    if vk == "validation" and missing:
        raise ValueError(
            f"{run_id} : marks partiels ({len(spec['data']['symbols']) - len(marks)}"
            f" symbole(s) sans marks : {missing}) — DD_UNKNOWN, refus de "
            "publier un risque officiel incomplet")
    if vk == "validation":
        per_window = wallet_per_window(events, proto, capital, cap_pct, lev,
                                       marks=marks)
        for wsub in per_window.values():
            # le détail trade-par-trade et la courbe horaire ne se
            # persistent pas (les métriques agrégées suffisent au rapport)
            wsub.pop("trade_pnls", None)
            wsub.pop("equity_hourly", None)
    # le moteur MTM quand les marks sont disponibles
    if marks:
        wallet = run_wallet_mtm(events, marks, capital=capital,
                                cap_pct=cap_pct, lev=lev,
                                span=(view.start_ms, view.end_ms))
    else:
        wallet = run_wallet(events, capital=capital, cap_pct=cap_pct, lev=lev)
    # PR-6/7 : effective-N + bootstrap TEMPOREL sur les rendements horaires
    tpnls = wallet.pop("trade_pnls", [])
    eqh = np.array([e for _, e in wallet.pop("equity_hourly", [])])
    eff = effective_sample_size(tpnls)
    if len(eqh) > 24:
        hr = eqh[1:] / eqh[:-1] - 1.0
        boot = block_bootstrap_hourly(hr, block_hours=24)
    else:
        boot = {"iters": 0, "note": "pas assez d'heures"}
    # PR-7 : le CONTRE-FACTUEL top-10 % — re-jouer le wallet SANS les 10 %
    # meilleurs trades (les tailles se recalculent), distinct de la
    # concentration de PnL (le simple retrait arithmétique)
    top = sorted(tpnls, key=lambda x: -x["net"])
    k10 = max(1, int(round(len(top) * 0.10))) if top else 0
    drop = {(tp.get("sym"), tp["t_ms"]) for tp in top[:k10]}
    evs_cf = [e for e in events if (e["sym"], e["t_ms"]) not in drop]
    if marks and evs_cf:
        wcf = run_wallet_mtm(evs_cf, marks, capital=capital,
                             cap_pct=cap_pct, lev=lev,
                             span=(view.start_ms, view.end_ms))
        counterfactual_sans_top10 = wcf["solde"]
        cf_liqs = wcf["liqs"]
    else:
        counterfactual_sans_top10 = wallet.get("solde")
        cf_liqs = wallet.get("liqs", 0)
    baseline = baseline_hold(spec, view, db_path=db_path, capital=capital)
    # PR-7 : la provenance du WALLET + le garde de cohérence spec_sha —
    # le manifest, le summary de la vue et la spec.json doivent pointer
    # vers la MÊME spec, sinon refus de publier (un wallet sans provenance
    # n'est pas un objet scientifique)
    sha_disk = rr.spec_sha(spec)
    mfile = RUNS / run_id / "manifest.json"
    m = json.loads(mfile.read_text(encoding="utf-8")) if mfile.exists() else {}
    target = "summary_confirmation.json" if vk == "validation" \
        else "summary_discovery.json"
    tfile = RUNS / run_id / target
    t_sha = json.loads(tfile.read_text(encoding="utf-8")).get("spec_sha") \
        if tfile.exists() else None
    if t_sha is not None and (m.get("spec_sha") != t_sha
                              or t_sha != sha_disk):
        raise ValueError(
            f"{run_id} : incohérence de provenance — manifest "
            f"{m.get('spec_sha')} vs {target} {t_sha} vs spec.json "
            f"{sha_disk} — refus de publier le wallet")
    prov = rr._provenance()
    out = {"run_id": run_id, "view": vk, "capital": capital,
           "cap_pct": cap_pct, "lev": lev, "frozen_src": frozen_src,
           "embargo_ms": embargo_ms if vk == "validation" else 0,
           "n_events": len(events), "fund_cov": fund_cov,
           "wallet": wallet, "baseline": baseline,
           "effective_n": eff, "bootstrap": boot,
           "counterfactual_sans_top10": counterfactual_sans_top10,
           "counterfactual_liqs": cf_liqs,
           "provenance": {"git_sha": prov["git_sha"],
                          "git_dirty": prov["git_dirty"],
                          "diff_sha": prov["diff_sha"],
                          "spec_sha": sha_disk,
                          "snapshot": m.get("snapshot"),
                          "portfolio_metrics_version": "pr7-v1"},
           "provenance_warning": (m.get("git_sha") != prov["git_sha"]
                                  or bool(prov["git_dirty"])),
           "per_window": per_window,
           "max_window_loss_pct": float(proto.get("max_window_loss_pct", 15))}
    if per_window:
        out["window_dd_breach"] = [
            k for k, w in per_window.items()
            if w["max_dd_pct"] > out["max_window_loss_pct"]]
        # C4 (bug-hunter ronde 4) : une fenêtre à DD INCONNU (marks
        # partiels, dd_status=UNKNOWN) n'est pas un dépassement MESURÉ —
        # mais le fail-open du filtre (nan > plafond = False) la rendait
        # invisible dans le rapport officiel, en contradiction avec le
        # gate fail-closed du confirm (FIX v14 : un DD inconnu n'est plus
        # un PASS). Le rapport la NOMME explicitement.
        out["window_dd_unknown"] = [
            k for k, w in per_window.items()
            if w.get("dd_status") == "UNKNOWN"]
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
            f"{wl['max_margin_used_pct']:.1f} % de l'équité |",
            f"| CAGR / Sharpe portefeuille / Sortino portefeuille | "
            f"{wl.get('cagr_pct', float('nan')):+.1f} % / "
            f"{wl.get('portfolio_sharpe') if wl.get('portfolio_sharpe') is not None else float('nan'):.2f} / "
            f"{wl.get('portfolio_sortino') if wl.get('portfolio_sortino') is not None else float('nan'):.2f} |",
            f"| profit factor / Sortino trade-level (secondaire) | "
            f"{wl.get('profit_factor', float('nan')):.2f} / "
            f"{wl.get('trade_sortino') if wl.get('trade_sortino') is not None else float('nan'):.1f} |",
            f"| concentration PnL sans top 1 / 5 / 10 % | ${wl.get('solde_sans_top1', wl['solde']):.2f} / "
            f"${wl.get('solde_sans_top5', wl['solde']):.2f} / "
            f"${wl.get('solde_sans_top10', wl['solde']):.2f} |",
            f"| CONTRE-FACTUEL sans top 10 % (re-joué, tailles recalculées) | "
            f"${w.get('counterfactual_sans_top10', wl['solde']):.2f} "
            f"(liq {w.get('counterfactual_liqs', 0)}) |"]
    bs = w.get("bootstrap") or {}
    if bs.get("iters"):
        en = w.get("effective_n", {})
        lines += [
            f"| n brut / sans chevauchement / effectif | "
            f"{en.get('n_raw')} / {en.get('n_nonoverlap')} / "
            f"{en.get('effective_n')} (autocorr {en.get('autocorr_1') if en.get('autocorr_1') is not None else float('nan'):+.3f}"
            f" · {en.get('n_time_buckets')} buckets horaires) |",
            f"| bootstrap mean CI95 (par heure) | "
            f"[{bs['mean_ci95'][0] * 10000:+.1f}, "
            f"{bs['mean_ci95'][1] * 10000:+.1f}] bps/h |",
            f"| bootstrap Sharpe portefeuille CI95 / t-stat CI95 | "
            f"[{bs['sharpe_ci95'][0]:+.2f}, {bs['sharpe_ci95'][1]:+.2f}] / "
            f"[{bs['t_stat_ci95'][0]:+.1f}, {bs['t_stat_ci95'][1]:+.1f}] |",
            f"| masse bootstrap mean > 0 | "
            f"{bs['n_neg_mean']} réplications négatives / "
            f"{bs['n_replications']} (blocs {bs['block_hours']} h) |"]
    if bl and bl.get("solde") == bl.get("solde"):
        lines.append(
            f"| baseline long-and-hold 1x | ${bl['solde']:.2f} "
            f"(ROI {bl['roi_pct']:+.2f} %, DD {bl['max_dd_pct']:.2f} %) — "
            "l'edge doit BATTRE ça |")
    if w.get("per_window"):
        def _dd_cell(v: dict) -> str:
            # C4 : « nan % » n'est pas un chiffre — le DD d'une fenêtre à
            # marks partiels est INCONNU, on l'écrit, on ne l'imprime pas
            # comme une valeur
            if v.get("dd_status") == "UNKNOWN" or np.isnan(v["max_dd_pct"]):
                return "INCONNU (marks partiels)"
            return f"{v['max_dd_pct']:.2f} %"
        pw = " · ".join(
            f"{k} {_dd_cell(v)}" for k, v in w["per_window"].items())
        lines.append(f"| DD par fenêtre gelée | {pw} "
                     f"(plafond {w['max_window_loss_pct']:.0f} %) |")
        if w.get("window_dd_breach"):
            lines.append(f"| ⚠️ DÉPASSEMENT plafond DD | "
                         f"{', '.join(w['window_dd_breach'])} |")
        if w.get("window_dd_unknown"):
            lines.append(f"| ⚠️ DD INCONNU (marks partiels — le gate de "
                         f"confirmation refuse ces fenêtres) | "
                         f"{', '.join(w['window_dd_unknown'])} |")
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
        if w.get("window_dd_unknown"):
            print(f"  ⚠️ DD INCONNU (marks partiels) : "
                  f"{', '.join(w['window_dd_unknown'])}")
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
