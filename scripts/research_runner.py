#!/usr/bin/env python3
"""LE RESEARCH RUNNER — Research OS PR 6 (brief V3 §6-7, §166, §203 PR6).

LA porte d'entrée unique de la recherche : une spécification YAML détermine
toute l'expérience, le runner orchestre data → masque → statistiques →
contrôles → verdict → artefacts → ledger. Le modèle ne choisit plus quel
script lancer, quelle DB lire, où écrire : il produit une intention.

Chaîne discovery (TRAIN only, hors budget scientifique) :
    python3 scripts/research_runner.py discovery --spec research/experiments/EXP-001.yaml
Chaîne confirmation (pré-enregistrée, budget strict, protocole-v2) :
    python3 scripts/research_runner.py confirm --spec research/experiments/EXP-001.yaml
Portefeuille (le wallet 100 $ d'un run — couche PR-B) :
    python3 scripts/research_runner.py portfolio --id EXP-001 [--view validation]
Comparaison :
    python3 scripts/research_runner.py compare EXP-A EXP-B
Statut :
    python3 scripts/research_runner.py status

Le masque de signal est évalué CAUSALEMENT : le seuil d'une feature est le
quantile EXPANDING des valeurs passées (warmup 50) — un trade ancien ne
connaît jamais la distribution future (leçon C10). La découverte ne voit
que la vue TRAIN du DataScope et gèle ses seuils ; la confirmation JUGE
SOUS PROTOCOLE (research/protocols/active.yaml) : fenêtres gelées évaluées
une par une (windows_pass_required), seuils gelés (jamais re-calibrés sur
la validation), embargo 72h, stress de coûts ×1,5, dégradation bornée —
et CONSOMME un slot (journal d'états + lab_ledger).

Artefacts par run : research/runs/<id>/ avec spec.json (copie gelée),
manifest.json (git sha, spec sha, label hash, snapshot), summary (les
chiffres utiles au LLM), report.md (le rapport humain + le bloc WALLET
quand la confirmation passe). Reproductible par experiment_id + git_sha +
spec_sha + label_hash (brief §41).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.aster_indicators import volume_z  # noqa: E402
from scripts.label_matrix import build_matrix, snapshot_id  # noqa: E402
from scripts.research_os import (  # noqa: E402
    DataScope, DataView, Mode, ScopeViolation, load_confirmation_protocol)

KDB = ROOT / "data" / "warehouse" / "klines.db"
RUNS = ROOT / "research" / "runs"
JOURNAL = ROOT / "research" / "ledger" / "experiments.jsonl"
WARMUP = 50


# ------------------------------------------------------------------ spec
def load_spec(path: Path) -> dict:
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for k in ("id", "hypothesis", "data", "signal", "horizons"):
        if k not in spec:
            raise ValueError(f"spec incomplète : champ requis manquant '{k}'")
    d = spec["data"]
    for k in ("symbols", "train_start", "train_end", "validation_start",
              "validation_end"):
        if k not in d:
            raise ValueError(f"spec.data incomplète : '{k}' manquant")
    return spec


def spec_sha(spec: dict) -> str:
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def _git() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()
    except OSError:
        return "?"


# ------------------------------------------------------------------ données
def compute_features(con: sqlite3.Connection, sym: str) -> dict[str, np.ndarray]:
    """Les features causales par barre 1h : range_pct, volume_z, ret_1h.
    Toutes connues au CLOSE de leur barre (availability = close_t)."""
    rows = con.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines "
        "WHERE symbol=? AND interval='1h' ORDER BY open_time",
        (sym,)).fetchall()
    if len(rows) < 60:
        raise ValueError(f"{sym} : pas assez de klines ({len(rows)})")
    ts = np.array([r[0] * 10**6 for r in rows], dtype=np.int64)
    o = np.array([r[1] for r in rows])
    h = np.array([r[2] for r in rows])
    l = np.array([r[3] for r in rows])
    c = np.array([r[4] for r in rows])
    v = pd.Series([r[5] for r in rows])
    cs = pd.Series(c)
    # fund_last : le dernier taux de funding CONNU au moment de la barre
    # (as-of strict, searchsorted — le print futur ne fuite pas)
    # FIX v6 : funding ABSENT ≠ funding nul. Le 0.0 inventé faisait matcher
    # les conditions « fund_last <= 0 » (le candidat H-01) sur des symboles
    # sans AUCUNE donnée de funding. NaN = inconnu, exclu des masques.
    fund_last = np.full(len(ts), np.nan)
    try:
        from scripts.funding_series import funding_series_for
        fser = funding_series_for(sym)
        if fser is not None and len(fser.times_ms):
            k = np.searchsorted(fser.times_ms / 1e6, ts / 1e6, side="right") - 1
            fund_last = np.where(k >= 0, fser.rates_pct[np.maximum(k, 0)], np.nan)
    except Exception:
        pass
    return {"open_time_ns": ts,
            "range_pct": (h - l) / c * 100.0,
            "volume_z": volume_z(v, n=20).values,
            "ret_1h": cs.pct_change().values * 100.0,
            "fund_last": fund_last}


def expanding_threshold(values: np.ndarray, q: float,
                        warmup: int = WARMUP) -> np.ndarray:
    """Le seuil EXPANDING : à la barre i, le quantile des valeurs passées.
    Causal par construction (leçon C10) ; NaN pendant le warmup."""
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        past = values[:i]
        if len(past) >= warmup:
            out[i] = np.nanquantile(past, q)
    return out


_THR_CACHE: dict[tuple, np.ndarray] = {}


def expanding_cached(values: np.ndarray, q: float, key: tuple | None) -> np.ndarray:
    """Le quantile expanding, mémoïsé par (db, symbole, feature, quantile).
    La boucle O(n²) ne doit payer qu'UNE fois par clé et par process —
    la confirmation multiplie les appels (train, fenêtres, stress)."""
    if key is not None and key in _THR_CACHE:
        return _THR_CACHE[key]
    out = expanding_threshold(values, q)
    if key is not None:
        _THR_CACHE[key] = out
    return out


def _mask_for(cols, fvals, op, thr, view):
    in_view = ((cols["open_time_ns"] >= view.start_ms * 10**6)
               & (cols["open_time_ns"] <= view.end_ms * 10**6))
    finite = np.isfinite(fvals) & (np.isfinite(thr) if np.ndim(thr) else True)
    base = (fvals >= thr) if op == ">=" else (fvals <= thr)
    return base & finite & in_view


def _signal_conditions(sig: dict) -> list[dict]:
    """Multi-conditions (Bonsai) ou mono-feature (legacy), même interface."""
    return list(sig["conditions"]) if "conditions" in sig else [sig]


def _multi_mask(feats: dict, conditions: list[dict], view, frozen=None,
                thr_key: tuple | None = None) -> np.ndarray:
    """Le masque ET de plusieurs conditions (brief V3 §7 de la spec).
    Chaque condition : {feature, op, quantile OU threshold}.
    Quantile = expanding (causal) ; threshold = valeur absolue déclarée.
    frozen = liste de seuils GELÉS alignée sur les conditions — la
    confirmation n'a pas le droit de re-calibrer un quantile SUR la
    validation (recalibrer sur le test = ré-estimer sur le test, rapport
    v6). Un seuil None (non gelable) → aucun event, conservateur."""
    n = len(next(iter(feats.values())))
    mask = np.ones(n, dtype=bool)
    for j, cond in enumerate(conditions):
        v = feats[cond["feature"]]
        if frozen is not None:
            ft = frozen[j] if j < len(frozen) else None
            if ft is None:
                mask &= np.zeros(n, dtype=bool)
            else:
                mask &= (v >= ft) if cond["op"] == ">=" else (v <= ft)
        elif "quantile" in cond:
            thr = expanding_cached(v, float(cond["quantile"]),
                                   (*thr_key, cond["feature"],
                                    float(cond["quantile"]))
                                   if thr_key else None)
            mask &= (v >= thr) if cond["op"] == ">=" else (v <= thr)
        else:
            mask &= ((v >= cond["threshold"]) if cond["op"] == ">="
                     else (v <= cond["threshold"])) & np.isfinite(v)
    in_view = ((feats["open_time_ns"] >= view.start_ms * 10**6)
               & (feats["open_time_ns"] <= view.end_ms * 10**6))
    return mask & in_view


def event_mask(spec: dict, feats: dict, view, frozen=None,
               min_event_ms: int = 0, thr_key: tuple | None = None) -> np.ndarray:
    """Le masque d'une spec sur les features d'UN symbole — le point
    partagé entre l'étude d'événement et la couche portefeuille."""
    sig = spec["signal"]
    if "conditions" in sig:
        mask = _multi_mask(feats, _signal_conditions(sig), view,
                           frozen=frozen, thr_key=thr_key)
    else:
        fvals = feats[sig["feature"]]
        if frozen is not None:
            ft = frozen[0] if frozen else None
            if ft is None:
                mask = np.zeros(len(fvals), dtype=bool)
            else:
                mask = _mask_for(cols=feats, fvals=fvals,
                                 op=sig.get("op", ">="),
                                 thr=np.full(len(fvals), float(ft)), view=view)
        else:
            q = float(sig.get("quantile", 0.95))
            thr = expanding_cached(fvals, q,
                                   (*thr_key, sig["feature"], q)
                                   if thr_key else None)
            mask = _mask_for(cols=feats, fvals=fvals, op=sig.get("op", ">="),
                             thr=thr, view=view)
    if min_event_ms:
        mask &= feats["open_time_ns"] >= min_event_ms * 10**6
    return mask


def _features_by_sym(spec: dict, db_path: Path) -> dict[str, dict]:
    """Les features causales par symbole, calculées UNE fois par run —
    la confirmation multiplie les études (train, fenêtres, stress)."""
    out = {}
    for sym in spec["data"]["symbols"]:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            out[sym] = compute_features(con, sym)
        finally:
            con.close()
    return out


def _frozen_thresholds(feats_by_sym: dict, conditions: list[dict],
                       view) -> dict[str, list[float | None]]:
    """Le seuil GELÉ par (symbole, condition) : la valeur du quantile
    expanding à la DERNIÈRE barre de la vue train. La confirmation réutilise
    CE nombre (artefact de découverte s'il existe, sinon recalcul TRAIN
    only) — les conditions à seuil absolu se gèlent telles quelles."""
    end_ns = view.end_ms * 10**6
    out = {}
    for sym, feats in feats_by_sym.items():
        vals: list[float | None] = []
        for cond in conditions:
            if "quantile" not in cond:
                vals.append(float(cond["threshold"]))
                continue
            v = feats[cond["feature"]]
            thr = expanding_cached(v, float(cond["quantile"]), None)
            idx = int(np.searchsorted(feats["open_time_ns"], end_ns,
                                      side="right")) - 1
            tv = thr[idx] if 0 <= idx < len(thr) else float("nan")
            vals.append(float(tv) if np.isfinite(tv) else None)
        out[sym] = vals
    return out


def _study(spec, matrix, view, side_mult: float, db_path: Path,
           feats_by_sym: dict | None = None, frozen: dict | None = None,
           min_event_ms: int = 0, cost_pct: float | None = None) -> dict:
    """L'étude d'événement sur la vue donnée (train, validation, fenêtre)."""
    from scripts.label_matrix import event_study
    sig = spec["signal"]
    side = int(sig.get("side", -1))
    cost = float(cost_pct if cost_pct is not None
                 else spec.get("cost_pct", 0.28))
    horizons = tuple(int(h) for h in spec.get("horizons", [24]))
    if feats_by_sym is None:
        feats_by_sym = _features_by_sym(spec, db_path)
    out = {}
    for sym in spec["data"]["symbols"]:
        if sym not in matrix or sym not in feats_by_sym:
            continue
        feats = feats_by_sym[sym]
        fz = frozen.get(sym) if frozen is not None else None
        if frozen is not None and fz is None:
            # symbole absent du gel → aucun seuil gelable → 0 event
            # (JAMAIS de re-calibration expanding sur la vue testée)
            fz = [None] * len(_signal_conditions(sig))
        mask = event_mask(spec, feats, view, frozen=fz,
                          min_event_ms=min_event_ms,
                          thr_key=(str(db_path), sym))
        if mask.any():
            view.assert_range(
                int(feats["open_time_ns"][mask][0]) // 10**6,
                int(feats["open_time_ns"][mask][-1]) // 10**6)
        for H in horizons:
            out[f"{sym}@{H}h"] = event_study(matrix[sym], mask, H,
                                             side=int(side * side_mult),
                                             cost_pct=cost)
    return out


def _aggregate(per_symbol: dict, min_n: int) -> tuple[int, float]:
    """La moyenne agrégée PONDÉRÉE par n (rapport v6) : une moyenne de
    moyennes non pondérée donnait le même poids à un symbole à 3 events
    qu'à un symbole à 3 000. n_total reste le compte toutes fenêtres."""
    kept = [(float(s["mean"]), int(s.get("n", 0)))
            for s in per_symbol.values() if s.get("n", 0) >= min_n]
    n_total = sum(int(s.get("n", 0)) for s in per_symbol.values())
    if not kept:
        return n_total, float("nan")
    w = np.array([n for _, n in kept], dtype=float)
    m = np.array([mu for mu, _ in kept], dtype=float)
    return n_total, float((m * w).sum() / w.sum())


# ------------------------------------------------------------------ runs
def run_discovery(spec: dict, db_path: Path = KDB) -> dict:
    """L'expérience DISCOVERY : vue TRAIN du DataScope uniquement, et
    production des seuils GELÉS que la confirmation réutilisera tels quels."""
    d = spec["data"]
    scope = DataScope(snapshot_id(db_path), int(d["train_start"]),
                      int(d["train_end"]), int(d["validation_start"]),
                      int(d["validation_end"]))
    view = scope.discovery_view()     # la validation n'y est pas résolvable
    use_cache = Path(db_path).resolve() == Path(KDB).resolve()
    lh, matrix = build_matrix(d["symbols"],
                              tuple(int(h) for h in spec.get("horizons", [24])),
                              db_path=db_path, use_cache=use_cache)
    try:
        feats_by_sym = _features_by_sym(spec, db_path)
        frozen = _frozen_thresholds(feats_by_sym,
                                    _signal_conditions(spec["signal"]), view)
        per_symbol = _study(spec, matrix, view, +1.0, db_path,
                            feats_by_sym=feats_by_sym)
    except ScopeViolation as exc:
        return {"verdict": "SCOPE_VIOLATION", "reason": str(exc)}
    min_n = int(spec.get("criteria", {}).get("min_n", 30))
    n_total, mean_all = _aggregate(per_symbol, min_n)
    # le contrôle inverse : le côté inversé doit être pire sur l'horizon 1
    inv = _study(spec, matrix, view, -1.0, db_path,
                 feats_by_sym=feats_by_sym)
    _, inv_mean = _aggregate({k: v for k, v in inv.items()
                              if k.endswith(f"@{spec.get('horizons', [24])[0]}h")},
                             min_n)
    verdict = ("DISCOVERY_PASS" if (n_total >= min_n
                                    and mean_all > float(spec.get("criteria",
                                                                 {}).get("min_mean", 0.0)))
               else "DISCOVERY_FAIL")
    return {"verdict": verdict, "n": n_total, "mean": mean_all,
            "inverse_mean": inv_mean, "per_symbol": per_symbol,
            "frozen_thresholds": frozen,
            "label_hash": lh, "snapshot": snapshot_id(db_path),
            "scope": {"mode": Mode.DISCOVERY.value,
                      "start": view.start_ms, "end": view.end_ms}}


# — le plancher d'events pour qu'une fenêtre de 2 mois démontre un signe —
WINDOW_MIN_N = 5


def _month_ms(m: str) -> int:
    dt = datetime.strptime(m, "%Y-%m").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _frozen_windows_ms(proto: dict) -> list[tuple[str, int, int]]:
    """Les fenêtres gelées d'active.yaml en (nom, start_ms, end_ms)."""
    return [(str(w["start"]), _month_ms(str(w["start"])),
             _month_ms(str(w["end"])))
            for w in proto.get("frozen_windows", [])]


def run_confirmation(spec: dict, db_path: Path = KDB,
                     protocol: dict | None = None) -> dict:
    """La CONFIRMATION sous protocole-v2 (rapport v6 — la porte conforme) :

      1. garde MODE : une spec déclarée « discovery » ne passe JAMAIS la
         porte (MODE_MISMATCH, 0 slot) ;
      2. les fenêtres : la validation de la spec doit couvrir les fenêtres
         gelées d'active.yaml, et l'évaluation est FAITE PAR FENÊTRE
         (verdict = ≥ windows_pass_required fenêtres PASS) — le verdict
         « CONFIRMED » d'une seule masse n'existe plus ;
      3. preflight (0 slot sur un échec d'infra, §47) ;
      4. seuils GELÉS depuis la découverte (artefact fait foi, sinon
         recalcul TRAIN only) + embargo à la frontière train→validation ;
      5. moyennes pondérées par n, dégradation train→validation ≤
         degradation_max_pct, et l'edge doit SURVIVRE au stress de coûts
         ×cost_stress_multiplier.

    max_window_loss_pct (15 %) s'applique au DD par fenêtre du WALLET —
    porté par la couche portefeuille (scripts/portfolio_runner.py).
    """
    d = spec["data"]
    if str(spec.get("mode", "confirmation")).lower() != "confirmation":
        return {"verdict": "MODE_MISMATCH", "slots_consumed": 0,
                "reason": (f"spec déclarée mode={spec.get('mode')!r} — la "
                           "confirmation est réservée aux specs pré-enregistrées "
                           "en mode confirmation")}
    proto = protocol if protocol is not None else load_confirmation_protocol()
    windows = _frozen_windows_ms(proto)
    vs, ve = int(d["validation_start"]), int(d["validation_end"])
    # chaque fenêtre gelée doit INTERSECTER la validation de la spec ; une
    # couverture partielle est tracée (coverage_pct) et rend la fenêtre
    # INÉLIGIBLE au PASS — une spec bâclée ne peut pas atteindre 5/6
    windows_cut: list[tuple[str, int, int, float]] = []
    for name, ws, we in windows:
        cs, ce_ = max(ws, vs), min(we, ve)
        if cs >= ce_:
            return {"verdict": "WINDOW_MISMATCH", "slots_consumed": 0,
                    "reason": (f"la fenêtre gelée {name} n'intersecte pas la "
                               "validation de la spec — research/protocols/"
                               "active.yaml est l'autorité (protocole-v2)")}
        windows_cut.append((name, cs, ce_, (ce_ - cs) / (we - ws) * 100.0))
    from scripts.preflight import preflight
    try:
        snap = snapshot_id(db_path)
    except sqlite3.Error:
        snap = "unknown"       # schéma cassé : preflight le dira, pas ici
    scope = DataScope(snap, int(d["train_start"]), int(d["train_end"]), vs, ve)
    pre = preflight(scope, d["symbols"], db_path=db_path)
    if pre["verdict"] != "PREFLIGHT_OK":
        return {"verdict": "PREFLIGHT_FAILED", "preflight": pre,
                "slots_consumed": 0}       # §47 : 0 slot sur un échec d'infra
    use_cache = Path(db_path).resolve() == Path(KDB).resolve()
    lh, matrix = build_matrix(d["symbols"],
                              tuple(int(h) for h in spec.get("horizons", [24])),
                              db_path=db_path, use_cache=use_cache)
    train_view, val_view = scope.confirmation_view()
    feats_by_sym = _features_by_sym(spec, db_path)
    conditions = _signal_conditions(spec["signal"])
    # — les seuils gelés : l'artefact de découverte fait foi ; à défaut,
    #   recalcul sur le TRAIN uniquement (jamais sur la validation) —
    frozen, frozen_src = None, "recomputed_train"
    sfile = RUNS / str(spec["id"]) / "summary_discovery.json"
    if sfile.exists():
        s = json.loads(sfile.read_text(encoding="utf-8"))
        if s.get("frozen_thresholds"):
            frozen, frozen_src = s["frozen_thresholds"], "discovery_artifact"
    if frozen is None:
        frozen = _frozen_thresholds(feats_by_sym, conditions, train_view)
    embargo_ms = (int(d["train_end"])
                  + int(proto.get("embargo_hours", 0)) * 3_600_000)
    cost = float(spec.get("cost_pct", 0.28))
    stress_mult = float(proto.get("cost_stress_multiplier", 1.5))
    deg_max = float(proto.get("degradation_max_pct", 70))
    need = int(proto.get("windows_pass_required", 5))
    h1 = int(spec.get("horizons", [24])[0])
    min_n = int(spec.get("criteria", {}).get("min_n", 30))

    # — le train : la référence de dégradation (seuils expanding sur le
    #   passé, identiques à la découverte) —
    tr = _study(spec, matrix, train_view, +1.0, db_path,
                feats_by_sym=feats_by_sym)
    _, tr_mean = _aggregate({k: v for k, v in tr.items()
                             if k.endswith(f"@{h1}h")}, min_n)

    # — les fenêtres gelées, une par une, seuils gelés + embargo —
    per_window: dict[str, dict] = {}
    for name, ws, we, cov in windows_cut:
        wview = DataView(snap, Mode.CONFIRMATION.value, ws, we)
        wst = _study(spec, matrix, wview, +1.0, db_path,
                     feats_by_sym=feats_by_sym, frozen=frozen,
                     min_event_ms=embargo_ms)
        n_w, mean_w = _aggregate({k: v for k, v in wst.items()
                                  if k.endswith(f"@{h1}h")}, min_n=WINDOW_MIN_N)
        eligible = cov >= 99.9     # une fenêtre tronquée ne démontre rien
        per_window[name] = {"n": n_w, "mean": mean_w,
                            "coverage_pct": cov, "eligible": eligible,
                            "pass": bool(eligible and n_w >= WINDOW_MIN_N
                                         and mean_w > 0.0)}

    # — la validation d'un bloc : l'agrégat + le stress de coûts —
    val = _study(spec, matrix, val_view, +1.0, db_path,
                 feats_by_sym=feats_by_sym, frozen=frozen,
                 min_event_ms=embargo_ms)
    val_h1 = {k: v for k, v in val.items() if k.endswith(f"@{h1}h")}
    n_total, val_mean = _aggregate(val_h1, min_n)
    stress = _study(spec, matrix, val_view, +1.0, db_path,
                    feats_by_sym=feats_by_sym, frozen=frozen,
                    min_event_ms=embargo_ms, cost_pct=cost * stress_mult)
    _, stress_mean = _aggregate({k: v for k, v in stress.items()
                                 if k.endswith(f"@{h1}h")}, min_n)
    deg = float("nan")
    if np.isfinite(tr_mean) and tr_mean > 0 and np.isfinite(val_mean):
        deg = (tr_mean - val_mean) / tr_mean * 100.0

    n_pass = sum(1 for w in per_window.values() if w["pass"])
    min_mean = float(spec.get("criteria", {}).get("min_mean", 0.0))
    verdict = ("CONFIRMED" if (n_total >= min_n and val_mean > min_mean
                               and n_pass >= need
                               and stress_mean > 0.0
                               and (not np.isfinite(deg) or deg <= deg_max))
               else "REJECTED")
    return {"verdict": verdict, "n": n_total, "mean": val_mean,
            "train_mean": tr_mean, "degradation_pct": deg,
            "stress_mean": stress_mean, "stress_multiplier": stress_mult,
            "per_window": per_window, "windows_pass": n_pass,
            "windows_required": need, "embargo_ms": embargo_ms,
            "frozen_src": frozen_src, "per_symbol": val,
            "slots_consumed": 1, "label_hash": lh, "snapshot": snap,
            "validation_window": [val_view.start_ms, val_view.end_ms]}


# ------------------------------------------------------------------ artefacts
def write_artifacts(run_id: str, spec: dict, result: dict, kind: str,
                    db_path: Path = KDB) -> Path:
    rdir = RUNS / run_id
    rdir.mkdir(parents=True, exist_ok=True)
    sha = spec_sha(spec)
    (rdir / "spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")
    snap = result.get("snapshot")
    if snap is None:
        try:
            snap = snapshot_id(db_path)
        except sqlite3.Error:
            snap = "unknown"   # DB absente (CI) : le manifest reste écrit
    (rdir / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "kind": kind, "spec_sha": sha, "git_sha": _git(),
        "label_hash": result.get("label_hash"), "snapshot": snap,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "per_symbol"}
    summary.update({"run_id": run_id, "spec_sha": sha,
                    "per_symbol": result.get("per_symbol", {})})
    (rdir / f"summary_{kind}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=float),
        encoding="utf-8")
    lines = [f"# {run_id} — {kind}", "",
             f"Hypothèse : {spec.get('hypothesis', '')}", "",
             f"- spec_sha {sha} · git {_git()} · snapshot {snap}",
             f"- verdict : **{result.get('verdict')}** · n {result.get('n')} · "
             f"mean {result.get('mean')}", ""]
    for key, st in result.get("per_symbol", {}).items():
        lines.append(f"- {key} : n {st.get('n')} · mean "
                     f"{float(st.get('mean', float('nan'))):.3f}")
    (rdir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rdir


def _log_ledger(spec: dict, verdict: str, mode: str, ref: str) -> None:
    subprocess.run([
        sys.executable, "scripts/lab_ledger.py", "log",
        "--family", str(spec.get("family", "research")),
        "--strategy", str(spec.get("strategy", "runner")),
        "--hypothesis", str(spec.get("hypothesis", ""))[:300],
        "--verdict", verdict, "--mode", mode,
        "--snapshot", str(snapshot_id()), "--ref", ref],
        check=False, cwd=ROOT)


# ------------------------------------------------------------------ CLI
def cmd_discovery(a) -> int:
    spec = load_spec(Path(a.spec))
    res = run_discovery(spec, db_path=Path(a.db))
    rdir = write_artifacts(spec["id"], spec, res, "discovery", db_path=Path(a.db))
    _log_ledger(spec, res["verdict"], Mode.DISCOVERY.value,
                str(rdir / "report.md"))
    print(f"{spec['id']} : {res['verdict']} · n {res['n']} · mean "
          f"{res['mean']:.3f} · inverse {res['inverse_mean']:.3f}")
    print("DISCOVERY = TRAIN only — jamais promote sans confirmation.")
    return 0


def cmd_confirm(a) -> int:
    spec = load_spec(Path(a.spec))
    res = run_confirmation(spec, db_path=Path(a.db))
    if res["verdict"] in ("MODE_MISMATCH", "WINDOW_MISMATCH"):
        print(f"{spec['id']} : {res['verdict']} — 0 slot consommé\n"
              f"  {res.get('reason', '')}")
        return 1
    if res["verdict"] == "PREFLIGHT_FAILED":
        print(f"{spec['id']} : PREFLIGHT_FAILED — 0 slot consommé")
        for c in res["preflight"]["checks"]:
            if not c["ok"]:
                print(f"  [ÉCHEC] {c['check']} — {c['detail']}")
        return 1
    rdir = write_artifacts(spec["id"], spec, res, "confirmation",
                           db_path=Path(a.db))
    _log_ledger(spec, "FAIL" if res["verdict"] == "REJECTED" else "PASS",
                Mode.CONFIRMATION.value, str(rdir / "report.md"))
    pw = res.get("windows_pass")
    print(f"{spec['id']} : {res['verdict']} · n {res['n']} · mean "
          f"{res['mean']:.3f} · fenêtres {pw}/{res.get('windows_required')} "
          f"PASS · stress ×{res.get('stress_multiplier')} mean "
          f"{res.get('stress_mean', float('nan')):.3f} · slot consommé")
    if res["verdict"] == "CONFIRMED":
        # PR-B : le wallet 100 $ sur la validation, obligatoire au rapport
        try:
            from scripts.portfolio_runner import wallet_for_run, wallet_report_block
            w = wallet_for_run(spec["id"], db_path=Path(a.db))
            block = wallet_report_block(w)
            with open(rdir / "report.md", "a", encoding="utf-8") as fh:
                fh.write(block)
            wl = w["wallet"]
            print(f"  WALLET {wl['capital']:.0f}$ cap {w['cap_pct']:.1f} % "
                  f"lev {w['lev']:.0f}x : solde {wl['solde']:.2f}$ · DD "
                  f"{wl['max_dd_pct']:.2f} % · liq {wl['liqs']} · mois nég "
                  f"{wl['months_neg']}")
        except Exception as exc:      # le wallet ne doit jamais masquer le verdict
            print(f"  (wallet indisponible : {exc})")
    return 0


def cmd_compare(a) -> int:
    print(f"{'id':<28} {'n':>6} {'verdict':<18} {'mean':>8} {'inverse':>8}")
    for rid in a.ids:
        f = None
        for k in ("summary_discovery.json", "summary_confirmation.json"):
            if (RUNS / rid / k).exists():
                f = RUNS / rid / k
                break
        if f is None:
            print(f"{rid} : aucun summary")
            continue
        s = json.loads(f.read_text(encoding="utf-8"))
        print(f"{rid:<28} {s.get('n', 0):>6} {str(s.get('verdict')):<18} "
              f"{float(s.get('mean', float('nan'))):>8.3f} "
              f"{float(s.get('inverse_mean', float('nan'))):>8.3f}")
    print("\nrobust winner ≠ absolute winner : compare aussi inverse et n.")
    return 0


def _resource_guard() -> tuple[bool, str]:
    """Le gouverneur de ressources (brief V3 §27, §138) : une limite
    PHYSIQUE, pas un plafond arbitraire. RAM disponible et disque libre."""
    try:
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                mem[k] = int(v.strip().split()[0])  # kB
        avail_gb = mem.get("MemAvailable", 0) / 1024 / 1024
        if avail_gb < 1.0:
            return False, f"RAM disponible {avail_gb:.1f} Go < 1 Go — pause"
    except OSError:
        pass
    du = shutil.disk_usage(ROOT)
    if du.free / 1024**3 < 2.0:
        return False, f"disque libre {du.free / 1024**3:.1f} Go < 2 Go"
    return True, "OK"


def _stage1_screen(spec: dict, db_path: Path) -> dict:
    """STAGE 1 — le screen bon marché : l'horizon PRINCIPAL seulement."""
    mini = dict(spec)
    mini["horizons"] = [int(spec["horizons"][0])]
    return run_discovery(mini, db_path=db_path)


def _passes(res: dict, spec: dict) -> bool:
    crit = spec.get("criteria", {})
    return (res.get("n", 0) >= int(crit.get("min_n", 30))
            and (res.get("mean", float("nan")) > float(crit.get("min_mean", 0.0))))


def cmd_grind(a) -> int:
    """LE GRIND (brief V3 §167-169) : la queue → screen bon marché → prune
    → screen complet → candidats. Successive halving : le calcul cher est
    réservé aux hypothèses qui méritent du calcul (§25-26)."""
    q = Path(a.queue)
    # récursif (rapport v6) : les sous-dossiers de la queue (bonsai/…) sont
    # grindés aussi ; done/ reste exclu (les specs jugées ne re-passent pas)
    specs = [p for p in sorted(q.rglob("*"))
             if p.is_file() and p.suffix in (".yaml", ".yml", ".json")
             and "done" not in p.parts]
    if not specs:
        print(f"queue vide : {q}")
        return 0
    order = {"tiny": 0, "small": 1, "medium": 2, "large": 3}
    specs.sort(key=lambda f: order.get(
        (json.loads(f.read_text(encoding="utf-8")).get("compute", {})
         .get("class", "small")), 1))
    ok_guard, why = _resource_guard()
    if not ok_guard:
        print(f"grind : garde-fou ressources — {why} (pause, pas d'échec)")
        return 0
    survivors = []
    for f in specs:
        spec = load_spec(f)
        print(f"[grind] stage 1 : {spec['id']} — screen {spec['horizons'][0]}h",
              flush=True)
        r1 = _stage1_screen(spec, Path(a.db))
        if not _passes(r1, spec):
            print(f"[grind]   éliminé (stage 1 : n {r1.get('n')}, "
                  f"mean {r1.get('mean', float('nan')):.3f})")
            continue
        print(f"[grind] stage 2 : {spec['id']} — tous les horizons + inverse")
        r2 = run_discovery(spec, db_path=Path(a.db))
        if _passes(r2, spec):
            write_artifacts(spec["id"], spec, r2, "discovery")
            _log_ledger(spec, r2["verdict"], Mode.DISCOVERY.value,
                        str(RUNS / spec["id"] / "report.md"))
            survivors.append(spec["id"])
            print(f"[grind]   CANDIDATE discovery : {r2['verdict']} "
                  f"(n {r2['n']}, mean {r2['mean']:.3f})")
        else:
            print(f"[grind]   éliminé (stage 2)")
        ok_guard, why = _resource_guard()
        if not ok_guard:
            print(f"[grind] {why} — arrêt propre de la file")
            break
    print(f"\ngrind terminé : {len(survivors)} candidat(s) discovery "
          f"→ confirmation sur go du propriétaire (jamais promote automatiquement)")
    return 0


def _cluster_key(spec: dict) -> str:
    """La clé de MECHANISM CLUSTER (brief V3 §61-62) : même famille + même
    feature + même opérateur = une seule idée conceptuelle, peu importe les
    seuils (RSI 29/30/31 ne sont pas 3 idées)."""
    s = spec.get("signal", {})
    return (f"{spec.get('family', '?')}|{s.get('feature', '?')}|"
            f"{s.get('op', '?')}|{s.get('side', -1)}")


def _pareto_frontier(rows: list[dict]) -> list[dict]:
    """La frontière de Pareto sur (mean ↑, n ↑, worst ↑) — brief V3 §61."""
    front = []
    for r in rows:
        dominated = any(
            (o["mean"] >= r["mean"] and o["n"] >= r["n"] and o["worst"] >= r["worst"])
            and (o["mean"] > r["mean"] or o["n"] > r["n"] or o["worst"] > r["worst"])
            for o in rows if o is not r)
        if not dominated:
            front.append(r)
    return front


def cmd_select(a) -> int:
    """PR 9 : la sélection des candidats — clusters + Pareto + diversité +
    pression de sélection (brief V3 §63-64, §73). AUCUNE valeur de PASS ici :
    la sélection produit des CANDIDATS, la confirmation juge."""
    rows = []
    for f in sorted(RUNS.glob("*/summary_discovery.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        spec_f = RUNS / s.get("run_id", f.parent.name) / "spec.json"
        spec = json.loads(spec_f.read_text(encoding="utf-8")) if spec_f.exists() else {}
        rows.append({"id": s.get("run_id"), "n": s.get("n", 0),
                     "mean": s.get("mean", float("nan")),
                     "worst": s.get("worst", float("nan")),
                     "cluster": _cluster_key(spec)})
    if not rows:
        print("aucune discovery à sélectionner")
        return 0
    frontier = _pareto_frontier(rows)
    clusters: dict[str, list[dict]] = {}
    for r in frontier:
        clusters.setdefault(r["cluster"], []).append(r)
    picked = []
    for cl, items in clusters.items():
        items.sort(key=lambda r: -r["mean"])
        picked.extend(items[:a.per_cluster])   # la diversité : ≤ N par cluster
    pressure = len(rows)
    print(f"{pressure} discoveries considérées · {len(frontier)} sur la frontière "
          f"de Pareto · {len(clusters)} mécanismes clusters · {len(picked)} "
          f"candidats (≤ {a.per_cluster}/cluster)\n")
    for r in picked:
        pct = r["n"] / pressure * 100 if pressure else 0
        print(f"  {r['id']} : mean {r['mean']:.3f} · n {r['n']} · "
              f"cluster {r['cluster']} · pression {pct:.1f} %")
    if picked:
        print("\nbloc registry prêt à coller (la curation reste au "
              "propriétaire — le registre est un fichier de gouvernance) :")
        for r in picked:
            print(f"- id: {r['id']}\n  status: CANDIDATE\n"
                  f"  cluster: {r['cluster']}")
    print("\n⚠️ CANDIDAT ≠ PREUVE : la confirmation juge (le slot scientifique).")
    return 0


def cmd_status(a) -> int:
    import shutil
    runs = sorted(RUNS.glob("*/manifest.json")) if RUNS.exists() else []
    print(f"{len(runs)} run(s) :")
    for m in runs:
        d = json.loads(m.read_text(encoding="utf-8"))
        print(f"  {d.get('run_id')} [{d.get('kind')}] spec {d.get('spec_sha')} "
              f"· git {d.get('git_sha')} · snapshot {d.get('snapshot')}")
    return 0


def cmd_portfolio(a) -> int:
    from scripts.portfolio_runner import cli_portfolio
    return cli_portfolio(a)


def cmd_forward(a) -> int:
    """La 3e étape du protocole : la maturation des confirmés (PAPER)."""
    from scripts import research_forward
    if a.collect:
        ids = [a.id] if a.id else research_forward.confirmed_runs()
        for rid in ids:
            r = research_forward.collect(rid, db_path=Path(a.db))
            print(f"[forward] {rid} : {r['collected']} nouvel(s) event(s) · "
                  f"total {r.get('journal_total', '?')}")
        return 0
    ids = [a.id] if a.id else research_forward.confirmed_runs()
    for rid in ids:
        s = research_forward.status(rid, db_path=Path(a.db))
        m = s["maturation"]
        tr = s["trades_closed"]
        line = (f"{rid} : {s['events_journaled']} events · "
                f"{tr['n']} trades fermés")
        if tr["mean"] is not None:
            line += f" · mean {tr['mean']:+.3f} %/trade · WR {tr['wr']:.1f} %"
            if s["wallet"]:
                w = s["wallet"]
                line += (f" · wallet ${w['solde']:.2f} (DD "
                         f"{w['max_dd_pct']:.2f} %, liq {w['liqs']})")
        line += (f" · maturation {m['days']:.1f}/{m['days_required']:.0f} j · "
                 f"{'READY pour review' if m['ready'] else 'en cours'}")
        print(line)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d1 = sub.add_parser("discovery")
    d1.add_argument("--spec", required=True)
    d1.add_argument("--db", default=str(KDB))
    d2 = sub.add_parser("confirm")
    d2.add_argument("--spec", required=True)
    d2.add_argument("--db", default=str(KDB))
    d3 = sub.add_parser("compare")
    d3.add_argument("ids", nargs="+")
    gr = sub.add_parser("grind")
    gr.add_argument("--queue", default=str(ROOT / "research" / "queue"))
    gr.add_argument("--db", default=str(KDB))
    sel = sub.add_parser("select")
    sel.add_argument("--per-cluster", type=int, default=2)
    sub.add_parser("status")
    pf = sub.add_parser("portfolio",
                        help="le wallet 100 $ d'un run (couche portefeuille)")
    pf.add_argument("--id", required=True)
    pf.add_argument("--capital", type=float, default=100.0)
    pf.add_argument("--cap-pct", type=float, default=1.0,
                    help="marge max %% de l'équité par trade (défaut 1)")
    pf.add_argument("--lev", type=float, default=1.0)
    pf.add_argument("--view", choices=["train", "validation"], default=None)
    pf.add_argument("--baseline", action="store_true",
                    help="baseline equal-weight long-and-hold uniquement")
    pf.add_argument("--db", default=str(KDB))
    fw = sub.add_parser("forward",
                        help="la maturation des confirmés (collect/status)")
    fw.add_argument("--collect", action="store_true")
    fw.add_argument("--id", default=None)
    fw.add_argument("--db", default=str(KDB))
    a = ap.parse_args()
    return {"discovery": cmd_discovery, "confirm": cmd_confirm,
            "compare": cmd_compare, "status": cmd_status,
            "grind": cmd_grind, "select": cmd_select,
            "portfolio": cmd_portfolio, "forward": cmd_forward}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
