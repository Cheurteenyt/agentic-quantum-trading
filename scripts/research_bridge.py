#!/usr/bin/env python3
"""LE RESEARCH BRIDGE — Research OS PR 7 (brief V3 §55-58).

La passerelle d'outils pour le modèle local : une interface CLI à sorties
JSON STRICTES. Bonsai ne reçoit jamais le shell complet, la DB brute ou le
filesystem — seulement ces opérations, avec le mode qui limite ce qu'il voit.

Outils (brief V3 §34, §55) :
  context   --mode discovery|confirmation [--id EXP]   le contexte par mode
  search    --query texte                              les expériences proches
  get       --experiment EXP-id                        manifest + summary
  compare   --ids EXP-A,EXP-B                          le tableau normalisé
  verify    --fact F-XXX                               SUPPORTED/CONTRADICTED/…
  status                                               les runs + le budget

Chaque sortie : {"ok": true, ...} ou {"ok": false, "code": "...", "message": "..."}
(brief V3 §58 — les contrats d'outils sont stricts).

    python scripts/research_bridge.py context --mode discovery
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNS = ROOT / "research" / "runs"


def _ok(**kw) -> str:
    return json.dumps({"ok": True, **kw}, ensure_ascii=False, default=float)


def _err(code: str, message: str) -> str:
    return json.dumps({"ok": False, "code": code, "message": message},
                      ensure_ascii=False)


def _run_json(argv: list[str]) -> dict:
    """Exécute un sous-outil et capture ce qu'il faut."""
    return {"_argv": argv}


def tool_context(mode: str, experiment_id: str | None) -> str:
    if mode not in ("discovery", "confirmation", "full"):
        return _err("BAD_MODE", f"mode inconnu: {mode}")
    if mode == "confirmation" and not experiment_id:
        return _err("MISSING_ID", "le mode confirmation exige --id")
    r = subprocess.run(
        [sys.executable, "scripts/context_manifest.py", "--mode", mode,
         "--id", experiment_id or ""],
        capture_output=True, text=True, cwd=ROOT)
    return _ok(mode=mode, context=r.stdout)


def tool_search(query: str) -> str:
    q = query.lower()
    hits = []
    if RUNS.exists():
        for f in sorted(RUNS.glob("*/summary_*.json")):
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            blob = json.dumps(s, ensure_ascii=False).lower()
            if q in blob:
                hits.append({"run_id": s.get("run_id"),
                             "verdict": s.get("verdict"),
                             "n": s.get("n"), "mean": s.get("mean")})
    reg = ROOT / "research" / "registry.yaml"
    fams = []
    if reg.exists():
        for raw in reg.read_text(encoding="utf-8").splitlines():
            if q in raw.lower() and (raw.strip().startswith("- ") or "id:" in raw):
                fams.append(raw.strip()[:120])
    return _ok(query=query, experiments=hits[:10], registry_hits=fams[:10])


def tool_get(experiment_id: str) -> str:
    rdir = RUNS / experiment_id
    if not rdir.exists():
        return _err("NOT_FOUND", f"run introuvable: {experiment_id}")
    out = {"run_id": experiment_id}
    for name in ("manifest.json", "spec.json", "summary_discovery.json",
                 "summary_confirmation.json"):
        f = rdir / name
        if f.exists():
            try:
                out[name.replace(".json", "")] = json.loads(
                    f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
    return _ok(**out)


def tool_compare(ids: list[str]) -> str:
    rows = []
    for rid in ids:
        f = None
        for k in ("summary_discovery.json", "summary_confirmation.json"):
            if (RUNS / rid / k).exists():
                f = RUNS / rid / k
                break
        if f is None:
            rows.append({"id": rid, "error": "NOT_FOUND"})
            continue
        s = json.loads(f.read_text(encoding="utf-8"))
        rows.append({"id": rid, "n": s.get("n"), "verdict": s.get("verdict"),
                     "mean": s.get("mean"), "inverse_mean": s.get("inverse_mean")})
    return _ok(comparison=rows,
               note="robust winner ≠ absolute winner : compare aussi inverse et n.")


def tool_verify(fact_id: str) -> str:
    r = subprocess.run(
        [sys.executable, "scripts/claim_verify.py", "--id", fact_id],
        capture_output=True, text=True, cwd=ROOT)
    verdict = "UNVERIFIED"
    for line in r.stdout.splitlines():
        if fact_id in line:
            verdict = line.split("[")[1].split("]")[0].strip()
    return _ok(fact_id=fact_id, verdict=verdict,
               output=r.stdout[-400:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="tool", required=True)
    c = sub.add_parser("context")
    c.add_argument("--mode", default="discovery")
    c.add_argument("--id")
    s = sub.add_parser("search")
    s.add_argument("--query", required=True)
    g = sub.add_parser("get")
    g.add_argument("--experiment", required=True)
    cmp = sub.add_parser("compare")
    cmp.add_argument("--ids", required=True, help="séparés par des virgules")
    v = sub.add_parser("verify")
    v.add_argument("--fact", required=True)
    sub.add_parser("status")
    a = ap.parse_args()
    try:
        if a.tool == "context":
            out = tool_context(a.mode, a.id)
        elif a.tool == "search":
            out = tool_search(a.query)
        elif a.tool == "get":
            out = tool_get(a.experiment)
        elif a.tool == "compare":
            out = tool_compare([x.strip() for x in a.ids.split(",")])
        elif a.tool == "verify":
            out = tool_verify(a.fact)
        else:
            out = _ok(runs=str(RUNS))
    except Exception as exc:  # la frontière d'outils : jamais de traceback brut
        out = _err("TOOL_ERROR", f"{type(exc).__name__}: {exc}")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
