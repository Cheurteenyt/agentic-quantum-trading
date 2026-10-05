#!/usr/bin/env python3
"""REGISTRY SYNC — le vérificateur de drift (audit GLM 5.3 post-#138).

Le registry.yaml est un fichier de GOUVERNANCE curé à la main (les
décisions restent au propriétaire) ; les chiffres qu'il cite doivent
cependant correspondre aux ARTEFACTS SCELLÉS de research/runs/. Ce module
ne réécrit RIEN : il émet les chiffres scellés par run et signale le drift
entre le registre et les artefacts.

    python3 scripts/registry_sync.py --check    # le drift, run par run
    python3 scripts/registry_sync.py --emit     # le bloc yaml scellé
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNS = ROOT / "research" / "runs"


def sealed(run_id: str) -> dict | None:
    """Les chiffres scellés d'un run — la source de vérité mécanique."""
    rdir = RUNS / run_id
    if not rdir.exists():
        return None
    out: dict = {"run_id": run_id}
    for kind in ("discovery", "confirmation"):
        f = rdir / f"summary_{kind}.json"
        if f.exists():
            try:
                s = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            out[kind] = {"verdict": s.get("verdict"),
                         "n": s.get("n"), "mean": s.get("mean"),
                         "stress_mean": s.get("stress_mean"),
                         "windows_pass": s.get("windows_pass"),
                         "spec_sha": s.get("spec_sha"),
                         "protocol_id": s.get("protocol_id")}
    w = rdir / "wallet.json"
    if w.exists():
        try:
            d = json.loads(w.read_text(encoding="utf-8"))
            out["wallet"] = {"solde": d.get("wallet", {}).get("solde"),
                             "dd_mtm": d.get("wallet", {}).get("max_dd_pct"),
                             "liqs": d.get("wallet", {}).get("liqs"),
                             "view": d.get("view")}
        except json.JSONDecodeError:
            pass
    m = rdir / "manifest.json"
    if m.exists():
        try:
            mm = json.loads(m.read_text(encoding="utf-8"))
            out["git_sha"] = mm.get("git_sha")
            out["git_dirty"] = mm.get("git_dirty")
        except json.JSONDecodeError:
            pass
    return out


def all_sealed() -> dict[str, dict]:
    return {d.name: sealed(d.name) for d in sorted(RUNS.iterdir())
            if d.is_dir() and sealed(d.name)}


def check() -> int:
    """Le drift : les runs dont le manifest porte un git_sha différent du
    HEAD courant (des artefacts produits par un moteur périmé) ou un arbre
    sale — les chiffres y sont historiques, pas reproductibles."""
    from scripts.research_runner import _provenance
    prov = _provenance()
    head = prov["git_sha"]
    stale = []
    for rid, s in all_sealed().items():
        if s.get("git_sha") and s["git_sha"] != head:
            stale.append(rid)
    if stale:
        print(f"[drift] {len(stale)} run(s) produits par un autre état du "
              f"code (HEAD courant {head}) :")
        for rid in stale:
            print(f"  {rid} : git_sha {all_sealed()[rid].get('git_sha')}")
        print("→ re-run obligatoire avant de citer ces chiffres comme "
              "preuve du moteur courant.")
    else:
        print("[ok] tous les runs scellés proviennent du HEAD courant")
    return 0


def emit() -> int:
    import yaml
    print(yaml.safe_dump(all_sealed(), allow_unicode=True, sort_keys=True))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--emit", action="store_true")
    a = ap.parse_args()
    if a.check:
        return check()
    if a.emit:
        return emit()
    print("choisis --check ou --emit")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
