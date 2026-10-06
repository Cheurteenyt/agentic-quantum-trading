#!/usr/bin/env python3
"""RESEARCH INTEGRITY — le gate d'invariants scientifiques (audit GLM 5.3
post-#147, Bloc D). La CI logicielle dit « le code compile » ; ce script
dit « les artefacts de recherche se tiennent mutuellement ».

Invariants :
  I001  active.yaml parse + protocol_id présent
  I002  registry.yaml parse
  I003  STATE.md porte le bloc LEDGER
  I004  les manifests d'univers parsent + bornes ms cohérentes
  I005  toute spec déclarant un universe le résout
  I006  les confirmations scellées portent le protocole actif
  I007  par run confirmé : manifest/summary/spec.json mêmes spec_sha
  I008  les journaux forward n'existent que pour des runs confirmés

    python3 scripts/research_integrity.py     # exit 0 = PASS, 1 = FAIL
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNS = ROOT / "research" / "runs"
FAILURES: list[str] = []


def check(inv: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"[OK]       {inv}  {detail}")
    else:
        print(f"[ÉCHEC]    {inv}  {detail}")
        FAILURES.append(inv)


def main() -> int:
    # I001 — le protocole parse
    proto = {}
    try:
        proto = yaml.safe_load(
            (ROOT / "research" / "protocols" / "active.yaml").read_text(
                encoding="utf-8"))
        check("I001", bool(proto.get("protocol_id")),
              f"protocol_id {proto.get('protocol_id')}")
    except Exception as exc:
        check("I001", False, f"active.yaml illisible : {exc}")
        return finish()
    active = str(proto.get("protocol_id"))

    # I002 — le registry parse
    try:
        reg = yaml.safe_load(
            (ROOT / "research" / "registry.yaml").read_text(encoding="utf-8"))
        check("I002", isinstance(reg, dict) and "strategies" in reg,
              f"{len(reg.get('strategies', []))} stratégies")
    except Exception as exc:
        check("I002", False, f"registry illisible : {exc}")
        return finish()

    # I003 — le bloc LEDGER de STATE
    st = (ROOT / "research" / "STATE.md").read_text(encoding="utf-8")
    from scripts.lab_ledger import BEGIN as _LEDGER_BEGIN
    check("I003", _LEDGER_BEGIN in st, "bloc LEDGER présent")

    # I004 — les manifests d'univers
    udir = ROOT / "research" / "universe"
    ok4, detail4 = True, []
    if udir.exists():
        for f in sorted(udir.glob("*.yaml")):
            try:
                m = yaml.safe_load(f.read_text(encoding="utf-8"))
                for sym, e in (m.get("symbols") or {}).items():
                    fb, lb = e.get("first_bar_ms"), e.get("last_bar_ms")
                    if fb is None or lb is None or lb <= fb:
                        ok4 = False
                        detail4.append(f"{f.name}:{sym} bornes ms invalides")
            except Exception as exc:
                ok4 = False
                detail4.append(f"{f.name} illisible : {exc}")
    check("I004", ok4, "; ".join(detail4) or
          f"{len(list(udir.glob('*.yaml')))} manifest(s) valides")

    # I005 — les specs qui déclarent un univers le résolvent
    ok5, detail5 = True, []
    for f in sorted((ROOT / "research" / "experiments").glob("*.json")) + \
            sorted((ROOT / "research" / "queue").rglob("*.json")):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if s.get("universe"):
            u = udir / f"{s['universe']}.yaml"
            if not u.exists():
                ok5 = False
                detail5.append(f"{f.name} : univers {s['universe']} absent")
    check("I005", ok5, "; ".join(detail5) or "toutes résolues")

    # I006/I007/I008 — les runs scellés
    ok6 = ok7 = ok8 = True
    det6: list[str] = []
    det7: list[str] = []
    det8: list[str] = []
    confirmed: set[str] = set()
    if RUNS.exists():
        for rdir in sorted(RUNS.iterdir()):
            if not rdir.is_dir():
                continue
            sfile = rdir / "summary_confirmation.json"
            if not sfile.exists():
                continue
            try:
                s = json.loads(sfile.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            rid = rdir.name
            kind = "confirmation"
            if s.get("verdict") == "CONFIRMED":
                confirmed.add(rid)
                if str(s.get("protocol_id", "")) != active:
                    ok6 = False
                    det6.append(f"{rid} : protocole {s.get('protocol_id')}")
            # I007 : manifest vs summary vs spec.json — même spec_sha,
            # LORSQU'ILS ONT ÉTÉ ÉCRITS ENSEMBLE (manifest kind == kind du
            # summary). Un run dir mixte (re-discovery post-v14 sur un
            # candidat REJECTED) garde son summary historique : le manifest
            # kind=discovery ne doit pas être comparé à un summary de
            # confirmation d'une autre ère.
            mfile = rdir / "manifest.json"
            jfile = rdir / "spec.json"
            if mfile.exists() and jfile.exists() and s.get("spec_sha"):
                try:
                    m = json.loads(mfile.read_text(encoding="utf-8"))
                    same_era = m.get("kind") == kind
                    if same_era:
                        sha_disk = __import__("hashlib").sha256(
                            json.dumps(json.loads(
                                jfile.read_text(encoding="utf-8")),
                                sort_keys=True).encode()).hexdigest()[:16]
                        if not (m.get("spec_sha") == s.get("spec_sha")
                                == sha_disk):
                            ok7 = False
                            det7.append(
                                f"{rid} : manifest {m.get('spec_sha')} / "
                                f"summary {s.get('spec_sha')} / spec {sha_disk}")
                except (json.JSONDecodeError, OSError):
                    pass
    check("I006", ok6, "; ".join(det6) or
          f"{len(confirmed)} confirmation(s) sous {active}")
    check("I007", ok7, "; ".join(det7) or "spec_sha cohérents")

    fdir = ROOT / "research" / "forward"
    if fdir.exists():
        for j in sorted(fdir.glob("*.jsonl")):
            if j.stem not in confirmed:
                ok8 = False
                det8.append(j.name)
    check("I008", ok8, "; ".join(det8) or
          "journaux forward ⊆ confirmés actifs")

    return finish()


def finish() -> int:
    if FAILURES:
        print(f"\nRESEARCH INTEGRITY: FAIL — {len(FAILURES)} invariant(s) : "
              + ", ".join(FAILURES))
        return 1
    print("\nRESEARCH INTEGRITY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
