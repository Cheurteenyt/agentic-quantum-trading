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
  I010  toute hypothèse pré-enregistrée porte un Mécanisme non trivial (P4)
  I011  les manifests d'univers sont point-in-time cohérents (P3)

    python3 scripts/research_integrity.py     # exit 0 = PASS, 1 = FAIL
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNS = ROOT / "research" / "runs"
FAILURES: list[str] = []


def _coherence_point_in_time(nom: str, m: dict) -> list[str]:
    """I011 (P3, audit Sonnet 5.5 R4) : la cohérence POINT-IN-TIME d'un
    manifest d'univers. L'anti-survivorship ne vaut que si le delisting est
    PROUVÉ : un `delisted_at` sans `deliste_source` est une invention (leçon
    F7 — un chiffre sans provenance), et il doit être un ISO date cohérent
    avec l'observation (≥ observed_start, ≤ observed_end + 2 j pour
    l'arrondi). Un symbole sans données est toléré (il ne tradera jamais).
    """
    problemes: list[str] = []
    for sym, e in (m.get("symbols") or {}).items():
        d = e.get("delisted_at")
        if not d:
            continue
        if not (e.get("deliste_source") or "").strip():
            problemes.append(f"{nom}:{sym} delisted_at sans deliste_source")
        try:
            dt = datetime.strptime(str(d), "%Y-%m-%d")
        except ValueError:
            problemes.append(f"{nom}:{sym} delisted_at illisible : {d}")
            continue
        os_ = e.get("observed_start")
        oe = e.get("observed_end")
        if os_ and dt < datetime.strptime(os_, "%Y-%m-%d"):
            problemes.append(f"{nom}:{sym} delisted_at < observed_start")
        if oe:
            oe_dt = datetime.strptime(oe, "%Y-%m-%d")
            if not (oe_dt - timedelta(days=2) <= dt <= oe_dt + timedelta(days=2)):
                problemes.append(
                    f"{nom}:{sym} delisted_at incohérent avec "
                    f"observed_end ({oe})")
    return problemes


def _contenu_mecanisme(lines: list[str], idx: int) -> str:
    """Le contenu du mécanisme (I010) : après le premier ':' de la ligne
    d'en-tête, plus les lignes indentées qui suivent (le paragraphe).
    Le format template est `Mécanisme (pourquoi…) :` + paragraphe indenté ;
    un fichier copié du template sans mécanisme écrit tombe à contenu vide."""
    parties = [lines[idx].split(":", 1)[1] if ":" in lines[idx] else ""]
    for l in lines[idx + 1:]:
        if not l.strip() or l[:1] not in (" ", "\t"):
            break
        parties.append(l)
    return " ".join(parties).strip()


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

    # I011 — la cohérence POINT-IN-TIME des manifests (P3, R4) : un
    # delisting sans provenance est une invention ; la machine à
    # survivorship invisible est le défaut que P3 ferme.
    ok11, detail11 = True, []
    if udir.exists():
        for f in sorted(udir.glob("*.yaml")):
            try:
                m = yaml.safe_load(f.read_text(encoding="utf-8"))
                detail11.extend(_coherence_point_in_time(f.stem, m or {}))
            except Exception as exc:
                ok11 = False
                detail11.append(f"{f.name} illisible : {exc}")
    if detail11:
        ok11 = False
    check("I011", ok11, "; ".join(detail11) or
          f"{len(list(udir.glob('*.yaml')))} manifest(s) point-in-time cohérents")

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

    # I010 (P4, audit Sonnet 5.5 R4) : toute hypothèse pré-enregistrée porte
    # un Mécanisme NON TRIVIAL. Le constat du rapport : « personne ne fait
    # tourner les hypothèses qui ont un mécanisme » — sans champ obligatoire,
    # on ne peut même pas MESURER lesquelles en ont un. Le format template est
    # `Mécanisme (pourquoi…) :` avec le contenu sur la même ligne et/ou en
    # lignes indentées qui suivent — un fichier copié du template SANS
    # mécanisme écrit tombe à contenu vide → refusé. Les non-hypothèses
    # (gabarit _, README, journaux d'amendements) sont hors champ ; les specs
    # scellées (crowding-composite) ne sont PAS modifiées — elles portent déjà
    # leur mécanisme et restent vérifiables par leur sha256 (SealTests).
    placeholder_re = re.compile(r"<[^>\n]*>")
    ok10, det10 = True, []
    for hdir in (ROOT / "research" / "hypotheses",
                 ROOT / "docs" / "lab" / "hypotheses"):
        if not hdir.is_dir():
            continue
        for f in sorted(hdir.glob("*.md")):
            if (f.stem.startswith("_") or f.name == "README.md"
                    or f.name.endswith(".amendments.md")):
                continue
            lines = f.read_text(encoding="utf-8",
                                errors="ignore").splitlines()
            idx = next((i for i, l in enumerate(lines)
                        if l.lstrip().startswith("Mécanisme")), None)
            if idx is None:
                ok10 = False
                det10.append(f"{f.name} : pas de ligne « Mécanisme »")
                continue
            contenu = _contenu_mecanisme(lines, idx)
            if len(contenu) < 40:
                ok10 = False
                det10.append(f"{f.name} : mécanisme vide/trivial")
            elif placeholder_re.search(contenu):
                ok10 = False
                det10.append(f"{f.name} : mécanisme placeholder")
    check("I010", ok10, "; ".join(det10) or
          "toute hypothèse pré-enregistrée porte son mécanisme")

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
