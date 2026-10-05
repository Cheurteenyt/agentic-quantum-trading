#!/usr/bin/env python3
"""LE FORWARD DU RESEARCH OS — la 3e étape du protocole (PAPER).

La confirmation a jugé sur les fenêtres gelées (protocole-v2) ; le protocole
exige ensuite la MATURATION : 30 jours de données INÉDITES jugées au
forward (active.yaml → forward_confirmation : min_forward_sharpe 0.5,
min_forward_trades 100, min_vs_discovery 0.5, maturation_days 30). Ce
module fait vivre les candidats CONFIRMÉS sur le live :

  COLLECT  — chaque nuit, évalue le masque GELÉ sur les barres 1h fermées
             postérieures au validation_end (données que aucun fitting n'a
             jamais vues) et journalise les events déclenchés :
             research/forward/<run_id>.jsonl (append-only, idempotent par
             (symbole, open_time) — une nuit manquée ne perd rien).
  STATUS   — les trades fermés du forward : ret/MAE/funding mesurés depuis
             les klines brutes, stats courantes, mini-wallet (run_wallet de
             la couche portefeuille), et l'horloge de maturation.

Le forward opère VOLONTAIREMENT hors DataScope : les fenêtres gelées
s'arrêtent au validation_end — tout ce qui suit est par définition le test
en cours. Aucun seuil n'est re-calibré ici JAMAIS (frozen_thresholds de la
découverte, artefact fait foi). Le JUGEMENT final à maturité reste une
étape de protocole (le statut ne fait que PROJECTER) — jamais de promote
automatique.

Usage :
    python3 scripts/research_forward.py --collect          # tous les confirmés
    python3 scripts/research_forward.py --status --id EXP-xxx
    python3 scripts/research_runner.py forward --collect   # la même porte
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research_os import (  # noqa: E402
    DataView, Mode, load_confirmation_protocol)
from scripts import research_runner as rr  # noqa: E402
from scripts.portfolio_runner import run_wallet  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
RUNS = rr.RUNS
FORWARD_DIR = ROOT / "research" / "forward"
H_MS = 3_600_000


# ------------------------------------------------------------------ runs
def confirmed_runs(runs_dir: Path = RUNS) -> list[str]:
    """Tous les runs dont la confirmation sous protocole est CONFIRMED."""
    out = []
    if not runs_dir.exists():
        return out
    for f in sorted(runs_dir.glob("*/summary_confirmation.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if s.get("verdict") == "CONFIRMED":
            out.append(f.parent.name)
    return out


def _load_run(run_id: str, runs_dir: Path = RUNS) -> tuple[dict, dict | None, str]:
    rdir = runs_dir / run_id
    spec = json.loads((rdir / "spec.json").read_text(encoding="utf-8"))
    frozen, src = None, "missing"
    sfile = rdir / "summary_discovery.json"
    if sfile.exists():
        s = json.loads(sfile.read_text(encoding="utf-8"))
        if s.get("frozen_thresholds"):
            frozen, src = s["frozen_thresholds"], "discovery_artifact"
    confirmed_at = ""
    mfile = rdir / "manifest.json"
    if mfile.exists():
        m = json.loads(mfile.read_text(encoding="utf-8"))
        confirmed_at = str(m.get("timestamp", ""))
    return spec, frozen, confirmed_at


# ------------------------------------------------------------------ collect
def _journal_path(run_id: str, forward_dir: Path = FORWARD_DIR) -> Path:
    return forward_dir / f"{run_id}.jsonl"


def _read_journal(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def collect(run_id: str, db_path: Path = KDB, now_ms: int | None = None,
            runs_dir: Path = RUNS, forward_dir: Path = FORWARD_DIR) -> dict:
    """Les events du masque gelé sur les barres fermées INÉDITES (>
    validation_end), moins ceux déjà journalisés. Idempotent."""
    spec, frozen, _ = _load_run(run_id, runs_dir)
    if frozen is None:
        return {"run_id": run_id, "collected": 0,
                "reason": "pas de seuils gelés (summary_discovery absent)"}
    d = spec["data"]
    h1 = int(spec.get("horizons", [24])[0])
    val_end = int(d["validation_end"])
    snap = rr.snapshot_id(db_path)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        jpath = _journal_path(run_id, forward_dir)
        journal = _read_journal(jpath)
        seen = {(e["symbol"], e["open_time_ms"]) for e in journal}
        feats_by_sym = rr._features_by_sym(spec, db_path)
        # la dernière barre 1h ENTIÈREMENT fermée (open_time + 1h <= now)
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        last_closed = (now // H_MS - 1) * H_MS
        view = DataView(snap, Mode.PAPER.value, val_end + 1, last_closed)
        new_events = []
        for sym in d["symbols"]:
            feats = feats_by_sym.get(sym)
            if feats is None:
                continue
            fz = frozen.get(sym)
            if fz is None:
                fz = [None] * len(rr._signal_conditions(spec["signal"]))
            mask = rr.event_mask(spec, feats, view, frozen=fz,
                                 thr_key=(str(db_path), sym))
            idx = [i for i in range(len(mask)) if mask[i]
                   and (sym, int(feats["open_time_ns"][i] // 10**6)) not in seen]
            for i in idx:
                ot_ms = int(feats["open_time_ns"][i] // 10**6)
                entry_open = float(con.execute(
                    "SELECT open FROM klines WHERE symbol=? AND interval='1h' "
                    "AND open_time=?", (sym, ot_ms)).fetchone()[0])
                new_events.append({
                    "ts_collected": datetime.now(timezone.utc).isoformat(),
                    "symbol": sym, "open_time_ms": ot_ms,
                    "side": int(spec["signal"].get("side", -1)),
                    "horizon_h": h1, "entry_open": entry_open,
                    "frozen_src": "discovery_artifact"})
        if new_events:
            jpath.parent.mkdir(parents=True, exist_ok=True)
            with open(jpath, "a", encoding="utf-8") as fh:
                for e in new_events:
                    fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        return {"run_id": run_id, "collected": len(new_events),
                "journal_total": len(journal) + len(new_events),
                "last_closed_ms": last_closed}
    finally:
        con.close()


# ------------------------------------------------------------------ status
def _closed_trades(spec: dict, events: list[dict], db_path: Path,
                   now_ms: int) -> list[dict]:
    """Les events dont l'horizon est écoulé : ret/MAE/funding mesurés depuis
    les klines brutes (mêmes conventions que le kernel : entrée à l'open(i),
    sortie au close(i+H-1), MAE sur [i, i+H-1])."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    h1 = int(spec.get("horizons", [24])[0])
    side = int(spec["signal"].get("side", -1))
    cost = float(spec.get("cost_pct", 0.28))
    try:
        out = []
        for e in events:
            ot = e["open_time_ms"]
            if ot + h1 * H_MS > now_ms - H_MS:
                continue          # horizon pas encore écoulé
            rows = con.execute(
                "SELECT open_time, open, high, low, close FROM klines "
                "WHERE symbol=? AND interval='1h' AND open_time>=? "
                "AND open_time<? ORDER BY open_time",
                (e["symbol"], ot, ot + h1 * H_MS)).fetchall()
            if len(rows) < h1:
                continue          # klines incomplètes : pas encore jugeable
            entry = float(rows[0][1])
            exit_c = float(rows[h1 - 1][4])
            hi = max(float(r[2]) for r in rows)
            lo = min(float(r[3]) for r in rows)
            ret = (exit_c / entry - 1.0) * 100.0 if entry else float("nan")
            mae = ((hi / entry - 1.0) if side == -1 else (lo / entry - 1.0)) * 100.0
            try:
                from scripts.funding_series import funding_series_for as _fsf
                fs = _fsf(e["symbol"])
                if fs is not None and len(fs.times_ms):
                    import numpy as np
                    k0 = int(np.searchsorted(fs.times_ms / 1e6, ot, side="right"))
                    k1 = int(np.searchsorted(fs.times_ms / 1e6,
                                             ot + h1 * H_MS, side="right"))
                    fund = float(fs.rates_pct[k0:k1].sum())
                else:
                    fund = 0.0
            except Exception:
                fund = 0.0
            out.append({"sym": e["symbol"], "t_ms": ot,
                        "exit_ms": ot + h1 * H_MS, "side": side,
                        "ret_pct": ret, "mae_pct": mae, "fund_pct": fund,
                        "cost_pct": cost})
        return out
    finally:
        con.close()


def status(run_id: str, db_path: Path = KDB, now_ms: int | None = None,
           runs_dir: Path = RUNS, forward_dir: Path = FORWARD_DIR) -> dict:
    """La maturation d'un candidat : les trades fermés du forward, les
    stats courantes, le mini-wallet, l'horloge du protocole."""
    spec, frozen, confirmed_at = _load_run(run_id, runs_dir)
    journal = _read_journal(_journal_path(run_id, forward_dir))
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    proto = load_confirmation_protocol()
    fc = proto.get("forward_confirmation", {})
    days = None
    if confirmed_at:
        try:
            t0 = datetime.fromisoformat(confirmed_at.replace("Z", "+00:00"))
            days = (now / 1000 - t0.timestamp()) / 86400.0
        except ValueError:
            pass
    trades = _closed_trades(spec, journal, db_path, now)
    stats = {"n": len(trades), "mean": None, "wr": None, "sharpe": None}
    if trades:
        rets = [t["side"] * t["ret_pct"] + t["fund_pct"] * (1 if t["side"] == -1 else -1)
                - t["cost_pct"] for t in trades]
        stats["mean"] = sum(rets) / len(rets)
        stats["wr"] = sum(1 for r in rets if r > 0) / len(rets) * 100.0
        stats["sharpe"] = _sharpe_trades(rets, now, trades[0]["t_ms"])
        wallet = run_wallet(trades, capital=100.0,
                            cap_pct=1.0, lev=1.0)
        wallet = {k: wallet[k] for k in ("solde", "roi_pct", "max_dd_pct",
                                         "liqs", "trades", "wr_pct",
                                         "months_neg", "months_total",
                                         "ret_dd", "fees", "funding_net")}
    else:
        wallet = None
    need_days = float(fc.get("maturation_days", 30))
    need_trades = int(fc.get("min_forward_trades", 100))
    ready = bool(days is not None and days >= need_days
                 and stats["n"] >= need_trades)
    return {"run_id": run_id, "confirmed_at": confirmed_at,
            "events_journaled": len(journal), "trades_closed": stats,
            "wallet": wallet,
            "maturation": {"days": days, "days_required": need_days,
                           "trades": stats["n"], "trades_required": need_trades,
                           "ready": ready,
                           "note": "ready ⇒ review de protocole, JAMAIS promote "
                                   "automatique" if ready else
                                   "le temps est le validateur (docs/13)"}}


def _sharpe_trades(rets: list[float], now_ms: int, first_ms: int) -> float | None:
    """Sharpe ANNUALISÉ par la fréquence de trades OBSERVÉE (convention
    gates.py : mean/sd × sqrt(périodes/an), garde anti-bruit)."""
    n = len(rets)
    if n < 2:
        return None
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    sd = math.sqrt(var)
    scale = max(abs(mean), max((abs(r) for r in rets), default=0.0), 1e-12)
    if var <= (scale * 1e-9) ** 2 or sd == 0:
        return None
    span_days = max((now_ms - first_ms) / 86400_000.0, 1.0)
    per_year = n / span_days * 365.0
    return (mean / sd) * math.sqrt(per_year)


# ------------------------------------------------------------------ CLI
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--collect", action="store_true",
                    help="journaliser les events du masque gelé (inédit)")
    ap.add_argument("--status", action="store_true",
                    help="rapport de maturation")
    ap.add_argument("--id", default=None, help="un run (défaut : tous)")
    ap.add_argument("--db", default=str(KDB))
    a = ap.parse_args()
    ids = [a.id] if a.id else confirmed_runs()
    if not ids:
        print("aucun candidat CONFIRMÉ à faire mûrir")
        return 0
    rc = 0
    for rid in ids:
        if a.collect:
            r = collect(rid, db_path=Path(a.db))
            print(f"[forward] {rid} : {r['collected']} nouvel(s) event(s) "
                  f"journalisé(s) · total {r.get('journal_total', '?')}")
        if a.status or not a.collect:
            s = status(rid, db_path=Path(a.db))
            m = s["maturation"]
            tr = s["trades_closed"]
            line = (f"[forward] {rid} : {s['events_journaled']} events · "
                    f"{tr['n']} trades fermés")
            if tr["mean"] is not None:
                line += (f" · mean {tr['mean']:+.3f} %/trade · WR "
                         f"{tr['wr']:.1f} %")
                if s["wallet"]:
                    w = s["wallet"]
                    line += (f" · wallet ${w['solde']:.2f} (DD "
                             f"{w['max_dd_pct']:.2f} %, liq {w['liqs']})")
            line += (f"\n           maturation : {m['days']:.1f}/"
                     f"{m['days_required']:.0f} j · {m['trades']}/"
                     f"{m['trades_required']} trades · "
                     f"{'READY pour review' if m['ready'] else 'en cours'}")
            print(line)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
