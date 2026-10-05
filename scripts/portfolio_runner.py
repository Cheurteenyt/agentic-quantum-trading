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
    for sym in spec["data"]["symbols"]:
        if sym not in matrix or sym not in feats_by_sym:
            continue
        cols, feats = matrix[sym], feats_by_sym[sym]
        fz = frozen.get(sym) if frozen is not None else None
        if frozen is not None and fz is None:
            fz = [None] * len(rr._signal_conditions(sig))
        mask = rr.event_mask(spec, feats, view, frozen=fz,
                             min_event_ms=min_event_ms,
                             thr_key=(str(db_path), sym))
        ret = cols[f"ret_{h1}"]
        idx = np.flatnonzero(mask & np.isfinite(ret))
        hi = cols[f"hi_{h1}"]
        lo = cols[f"lo_{h1}"]
        fund = cols.get(f"fund_{h1}")
        for i in idx:
            fv = float(fund[i]) if fund is not None else 0.0
            if not np.isfinite(fv):
                fv = 0.0          # l'inconnu contribue 0 ; fund_cov le dit
            # MAE côté position, % : short souffre du high, long du low
            # (hi/lo du kernel sont des FRACTIONS → ×100)
            mae_pct = (float(hi[i]) * 100.0) if side == -1 \
                else (-float(lo[i]) * 100.0)
            t_ms = int(feats["open_time_ns"][i] // 10**6)
            events.append({
                "sym": sym, "t_ms": t_ms, "exit_ms": t_ms + h1 * 3_600_000,
                "side": side, "ret_pct": float(ret[i]),
                "mae_pct": mae_pct, "fund_pct": fv, "cost_pct": cost})
    events.sort(key=lambda e: e["t_ms"])
    return events


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
    for ev in events:
        if ev["t_ms"] < busy.get(ev["sym"], -1):
            skipped += 1
            continue
        margin = eq * cap_pct / 100.0
        if margin <= 0:
            break
        notional = margin * lev
        fund_signed = ev["fund_pct"] * (1.0 if ev["side"] == -1 else -1.0)
        if ev["mae_pct"] >= liq_thr:
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
            "cap_pct": cap_pct, "lev": lev}


def wallet_per_window(events: list[dict], proto: dict, capital: float,
                      cap_pct: float, lev: float) -> dict[str, dict]:
    """Le DD du wallet PAR FENÊTRE gelée — là où max_window_loss_pct
    (15 %) s'applique. Une fenêtre = des events bornés, un wallet reset."""
    out = {}
    for w in proto.get("frozen_windows", []):
        ws = rr._month_ms(str(w["start"]))
        we = rr._month_ms(str(w["end"]))
        evs = [e for e in events if ws <= e["t_ms"] < we]
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
                "AND interval='1h' AND open_time>=? AND open_time<=? "
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
    has_conf = (rdir / "summary_confirmation.json").exists()
    vk = view_kind or ("validation" if has_conf else "train")
    if vk == "validation" and not has_conf:
        raise ValueError(
            f"{run_id} : pas de confirmation — le wallet validation se "
            "mérite (un slot consommé). Utilisez --view train.")
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
        events = collect_events(spec, matrix, feats_by_sym, view,
                                frozen=None, min_event_ms=0, db_path=db_path)
        per_window = None
    else:
        view = scope.confirmation_view()[1]
        events = collect_events(spec, matrix, feats_by_sym, view,
                                frozen=frozen, min_event_ms=embargo_ms,
                                db_path=db_path)
        per_window = wallet_per_window(events, proto, capital, cap_pct, lev)
    wallet = run_wallet(events, capital=capital, cap_pct=cap_pct, lev=lev)
    baseline = baseline_hold(spec, view, db_path=db_path, capital=capital)
    out = {"run_id": run_id, "view": vk, "capital": capital,
           "cap_pct": cap_pct, "lev": lev, "frozen_src": frozen_src,
           "embargo_ms": embargo_ms if vk == "validation" else 0,
           "n_events": len(events), "wallet": wallet, "baseline": baseline,
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
             f"| DD max | {wl['max_dd_pct']:.2f} % |",
             f"| liquidations | {wl['liqs']} |",
             f"| WR | {wl['wr_pct']:.1f} % |",
             f"| mois négatifs | {wl['months_neg']} / {wl['months_total']} |",
             f"| pire mois / record | {wl['worst_month']:+.2f}$ / "
             f"{wl['best_month']:+.2f}$ |",
             f"| ret/DD | {wl['ret_dd']:.1f} |",
             f"| frais payés | ${wl['fees']:.2f} · funding net "
             f"${wl['funding_net']:+.2f} |"]
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
