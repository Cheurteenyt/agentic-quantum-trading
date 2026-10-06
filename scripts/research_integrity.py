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
            # I007 : manifest vs summary vs spec.json — même spec_sha.
            # FIX v19 (PR-155 №8, affiné) : STRICT pour les runs CONFIRMED
            # dont la découverte est DISCOVERY_PASS (candidat vivant). Un
            # run dont la découverte est DISCOVERY_FAIL (rejeté post-v14)
            # porte un summary_confirmation HISTORIQUE — sa vérification
            # n'a pas de sens (la confirmation vient d'un moteur périmé).
            dfile = rdir / "summary_discovery.json"
            d_verdict = None
            if dfile.exists():
                try:
                    d_verdict = json.loads(
                        dfile.read_text(encoding="utf-8")).get("verdict")
                except json.JSONDecodeError:
                    pass
            mfile = rdir / "manifest.json"
            jfile = rdir / "spec.json"
            if (s.get("verdict") == "CONFIRMED"
                    and d_verdict == "DISCOVERY_PASS"):
                # CONFIRMED : vérification TOUJOURS, sans exception
                if not mfile.exists() or not jfile.exists():
                    ok7 = False
                    det7.append(f"{rid} : manifest ou spec.json manquant")
                    continue
                try:
                    m = json.loads(mfile.read_text(encoding="utf-8"))
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
                except (json.JSONDecodeError, OSError) as exc:
                    ok7 = False
                    det7.append(f"{rid} : fichier illisible {exc}")
            else:
                # run non-CONFIRMED : vérification si les fichiers coexistent
                if mfile.exists() and jfile.exists() and s.get("spec_sha"):
                    try:
                        m = json.loads(mfile.read_text(encoding="utf-8"))
                        if m.get("kind") == "confirmation":
                            sha_disk = __import__("hashlib").sha256(
                                json.dumps(json.loads(
                                    jfile.read_text(encoding="utf-8")),
                                    sort_keys=True).encode()).hexdigest()[:16]
                            if m.get("spec_sha") != s.get("spec_sha"):
                                ok7 = False
                                det7.append(f"{rid} : SHA mismatch")
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

    # I009 (PR-150, durci PR-155 №9) : l'égalité est BIDIRECTIONNELLE —
    # CONFIRMED ⊆ ledger ET ledger ⊆ CONFIRMED, avec détection des
    # doublons (le set masquait les lignes multiples)
    ok9, det9 = True, []
    ledger = ROOT / "research" / "ledger" / "trials.jsonl"
    ledger_conf: dict[str, int] = {}   # run_id → count (doublons visibles)
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            ref = str(e.get("ref", ""))
            if e.get("mode") == "confirmation" and "/runs/" in ref:
                rid = ref.split("/runs/")[1].split("/")[0]
                ledger_conf[rid] = ledger_conf.get(rid, 0) + 1
    # CONFIRMED ⊆ ledger : chaque run confirmé a AU MOINS une ligne
    for rid in sorted(confirmed):
        if rid not in ledger_conf:
            ok9 = False
            det9.append(f"{rid} : CONFIRMED sans ligne ledger")
    # ledger ⊆ CONFIRMED : chaque ligne de confirmation pointe vers un run
    # qui existe ET dont le verdict est CONFIRMED (ou a été re-mesuré REJECTED
    # — le run dir est la vérité courante)
    for rid, count in sorted(ledger_conf.items()):
        rdir = RUNS / rid
        sfile = rdir / "summary_confirmation.json"
        if not rdir.exists():
            ok9 = False
            det9.append(f"{rid} : ligne ledger sans run dir")
        elif sfile.exists():
            try:
                sv = json.loads(sfile.read_text(encoding="utf-8")).get("verdict")
                if sv not in ("CONFIRMED", "REJECTED"):
                    det9.append(f"{rid} : verdict inattendu {sv}")
            except (json.JSONDecodeError, OSError):
                pass
    check("I009", ok9, "; ".join(det9) or
          f"{len(confirmed)} CONFIRMED(s) ↔ {len(ledger_conf)} ligne(s) ledger")

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
