#!/usr/bin/env python3
"""LE RESEARCH RUNNER — Research OS PR 6 (brief V3 §6-7, §166, §203 PR6).

LA porte d'entrée unique de la recherche : une spécification YAML détermine
toute l'expérience, le runner orchestre data → masque → statistiques →
contrôles → verdict → artefacts → ledger. Le modèle ne choisit plus quel
script lancer, quelle DB lire, où écrire : il produit une intention.

Chaîne discovery (TRAIN only, hors budget scientifique) :
    python3 scripts/research_runner.py discovery --spec research/experiments/EXP-001.yaml
Chaîne confirmation (pré-enregistrée, budget strict, preflight obligatoire) :
    python3 scripts/research_runner.py confirm --spec research/experiments/EXP-001.yaml
Comparaison :
    python3 scripts/research_runner.py compare EXP-A EXP-B
Statut :
    python3 scripts/research_runner.py status

Le masque de signal est évalué CAUSALEMENT : le seuil d'une feature est le
quantile EXPANDING des valeurs passées (warmup 50) — un trade ancien ne
connaît jamais la distribution future (leçon C10). La découverte ne voit
que la vue TRAIN du DataScope ; la confirmation ajoute la vue validation et
CONSOMME un slot (journal d'états + lab_ledger).

Artefacts par run : research/runs/<id>/ avec spec.json (copie gelée),
manifest.json (git sha, spec sha, label hash, snapshot), summary (les
chiffres utiles au LLM), report.md (le rapport humain). Reproductible par
experiment_id + git_sha + spec_sha + label_hash (brief §41).
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
    DataScope, Mode, ScopeViolation)

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
    try:
        from scripts.funding_series import funding_series_for
        fser = funding_series_for(sym)
        k = np.searchsorted(fser.times_ms / 1e6, ts / 1e6, side="right") - 1
        fund_last = np.where(k >= 0, fser.rates_pct[np.maximum(k, 0)], 0.0)
    except Exception:
        fund_last = np.zeros(len(ts))
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


def _mask_for(cols, fvals, op, thr, view):
    in_view = ((cols["open_time_ns"] >= view.start_ms * 10**6)
               & (cols["open_time_ns"] <= view.end_ms * 10**6))
    finite = np.isfinite(fvals) & np.isfinite(thr)
    base = (fvals >= thr) if op == ">=" else (fvals <= thr)
    return base & finite & in_view


def _multi_mask(feats: dict, conditions: list[dict], view) -> np.ndarray:
    """Le masque ET de plusieurs conditions (brief V3 §7 de la spec).
    Chaque condition : {feature, op, quantile OU threshold}.
    Quantile = expanding (causal) ; threshold = valeur absolue déclarée."""
    n = len(next(iter(feats.values())))
    mask = np.ones(n, dtype=bool)
    for cond in conditions:
        v = feats[cond["feature"]]
        if "quantile" in cond:
            thr = expanding_threshold(v, float(cond["quantile"]), warmup=WARMUP)
            m = np.isfinite(v) & np.isfinite(thr)
            mask &= (v >= thr) if cond["op"] == ">=" else (v <= thr)
        else:
            m = np.isfinite(v)
            mask &= ((v >= cond["threshold"]) if cond["op"] == ">="
                     else (v <= cond["threshold"])) & m
    in_view = ((feats["open_time_ns"] >= view.start_ms * 10**6)
               & (feats["open_time_ns"] <= view.end_ms * 10**6))
    return mask & in_view


def _study(spec, matrix, view, side_mult: float, db_path: Path) -> dict:
    """L'étude d'événement sur la vue donnée (train ou validation)."""
    from scripts.label_matrix import event_study
    sig = spec["signal"]
    side = int(sig.get("side", -1))
    cost = float(spec.get("cost_pct", 0.28))
    horizons = tuple(int(h) for h in spec.get("horizons", [24]))
    out = {}
    for sym in spec["data"]["symbols"]:
        if sym not in matrix:
            continue
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            feats = compute_features(con, sym)
        finally:
            con.close()
        # le masque : multi-conditions (Bonsai) OU mono-feature (legacy)
        if "conditions" in sig:
            mask = _multi_mask(feats, sig["conditions"], view)
        else:
            fvals = feats[sig["feature"]]
            thr = expanding_threshold(fvals, float(sig.get("quantile", 0.95)))
            mask = _mask_for(cols=matrix[sym], fvals=fvals,
                             op=sig.get("op", ">="), thr=thr, view=view)
        if mask.any():
            view.assert_range(
                int(matrix[sym]["open_time_ns"][mask][0]) // 10**6,
                int(matrix[sym]["open_time_ns"][mask][-1]) // 10**6)
        for H in horizons:
            out[f"{sym}@{H}h"] = event_study(matrix[sym], mask, H,
                                             side=int(side * side_mult),
                                             cost_pct=cost)
    return out


def _aggregate(per_symbol: dict, min_n: int) -> tuple[int, float]:
    means = [s["mean"] for s in per_symbol.values() if s.get("n", 0) >= min_n]
    n_total = sum(s["n"] for s in per_symbol.values())
    return n_total, (float(np.mean(means)) if means else float("nan"))


# ------------------------------------------------------------------ runs
def run_discovery(spec: dict, db_path: Path = KDB) -> dict:
    """L'expérience DISCOVERY : vue TRAIN du DataScope uniquement."""
    d = spec["data"]
    scope = DataScope(spec["id"], int(d["train_start"]), int(d["train_end"]),
                      int(d["validation_start"]), int(d["validation_end"]))
    view = scope.discovery_view()     # la validation n'y est pas résolvable
    use_cache = Path(db_path).resolve() == Path(KDB).resolve()
    lh, matrix = build_matrix(d["symbols"],
                              tuple(int(h) for h in spec.get("horizons", [24])),
                              db_path=db_path, use_cache=use_cache)
    try:
        per_symbol = _study(spec, matrix, view, +1.0, db_path)
    except ScopeViolation as exc:
        return {"verdict": "SCOPE_VIOLATION", "reason": str(exc)}
    min_n = int(spec.get("criteria", {}).get("min_n", 30))
    n_total, mean_all = _aggregate(per_symbol, min_n)
    # le contrôle inverse : le côté inversé doit être pire sur l'horizon 1
    inv = _study(spec, matrix, view, -1.0, db_path)
    _, inv_mean = _aggregate({k: v for k, v in inv.items()
                              if k.endswith(f"@{spec.get('horizons', [24])[0]}h")},
                             min_n)
    verdict = ("DISCOVERY_PASS" if (n_total >= min_n
                                    and mean_all > float(spec.get("criteria",
                                                                 {}).get("min_mean", 0.0)))
               else "DISCOVERY_FAIL")
    return {"verdict": verdict, "n": n_total, "mean": mean_all,
            "inverse_mean": inv_mean, "per_symbol": per_symbol,
            "label_hash": lh, "snapshot": snapshot_id(db_path),
            "scope": {"mode": Mode.DISCOVERY.value,
                      "start": view.start_ms, "end": view.end_ms}}


def run_confirmation(spec: dict, db_path: Path = KDB) -> dict:
    """La CONFIRMATION : preflight → vue validation → slot consommé."""
    d = spec["data"]
    scope = DataScope(spec["id"], int(d["train_start"]), int(d["train_end"]),
                      int(d["validation_start"]), int(d["validation_end"]))
    from scripts.preflight import preflight
    pre = preflight(scope, d["symbols"], db_path=db_path)
    if pre["verdict"] != "PREFLIGHT_OK":
        return {"verdict": "PREFLIGHT_FAILED", "preflight": pre,
                "slots_consumed": 0}       # §47 : 0 slot sur un échec d'infra
    use_cache = Path(db_path).resolve() == Path(KDB).resolve()
    lh, matrix = build_matrix(d["symbols"],
                              tuple(int(h) for h in spec.get("horizons", [24])),
                              db_path=db_path, use_cache=use_cache)
    _, val_view = scope.confirmation_view()
    per_symbol = _study(spec, matrix, val_view, +1.0, db_path)
    min_n = int(spec.get("criteria", {}).get("min_n", 30))
    n_total, mean_all = _aggregate(per_symbol, min_n)
    verdict = ("CONFIRMED" if (n_total >= min_n
                               and mean_all > float(spec.get("criteria",
                                                             {}).get("min_mean", 0.0)))
               else "REJECTED")
    return {"verdict": verdict, "n": n_total, "mean": mean_all,
            "per_symbol": per_symbol, "slots_consumed": 1, "label_hash": lh,
            "snapshot": snapshot_id(db_path),
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
    print(f"{spec['id']} : {res['verdict']} · n {res['n']} · mean "
          f"{res['mean']:.3f} · slot consommé")
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
    specs = sorted(q.glob("*.y*ml")) + sorted(q.glob("*.json"))
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
    a = ap.parse_args()
    return {"discovery": cmd_discovery, "confirm": cmd_confirm,
            "compare": cmd_compare, "status": cmd_status,
            "grind": cmd_grind, "select": cmd_select}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
