#!/usr/bin/env python
"""LE MANIFESTE DE CONTEXTE — Research Firewall, couche 2 (audit GPT v3 §26).

Le brief d'entrée d'une session : HEAD, l'état officiel (STATE.md), les faits
du ledger (research/evidence/facts.jsonl), l'état du budget, les derniers
verdicts. Une session lit CE manifeste au lieu de relire 127 Ko de registre —
et tout ce qu'il contient est vérifiable via scripts/claim_verify.py.

    python scripts/context_manifest.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "research" / "evidence" / "facts.jsonl"
STATE = ROOT / "research" / "STATE.md"
TRIALS = ROOT / "research" / "ledger" / "trials.jsonl"
RUNS = ROOT / "research" / "runs"


def _head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True, cwd=ROOT).stdout.strip()


def _budget() -> str:
    """La sortie du verrou anti-boucle (exit 0 = go, 4 = STOP)."""
    r = subprocess.run(
        [sys.executable, "scripts/lab_ledger.py", "check",
         "--family", "_", "--strategy", "_", "--hypothesis", "_manifest"],
        capture_output=True, text=True, cwd=ROOT)
    line = next((l for l in (r.stdout + r.stderr).splitlines()
                 if l.startswith("Semaine")), "budget : illisible")
    stop = "STOP" in (r.stdout + r.stderr)
    return f"{line} — {'STOP (file B)' if stop else 'GO'}"


def _dead_mechanisms() -> list[str]:
    """Les familles MORTES du registre — la connaissance négative que la
    découverte peut utiliser (le mécanisme est mort, pas le résultat de la
    validation utilisée comme signal de tuning — brief V3 §9, fuite B)."""
    out = []
    reg = ROOT / "research" / "registry.yaml"
    if not reg.exists():
        return out
    fam, dead = None, False
    for raw in reg.read_text(encoding="utf-8").splitlines():
        if raw.startswith("- id:") or raw.startswith("- name:"):
            if fam and dead:
                out.append(fam)
            fam = raw.split(":", 1)[1].strip().strip('\"')
            dead = False
        elif fam and "status:" in raw and ("REJECTED" in raw or "RETIRED" in raw):
            dead = True
    if fam and dead:
        out.append(fam)
    return out


def discovery_context() -> str:
    """Le contexte DISCOVERY — AVEUGLE à la validation (brief V3 §9, fuite B) :
    pas de verdicts de confirmation, pas de scores OOS, pas de résultats du
    holdout. Seulement : HEAD, les mécanismes morts, les primitives, la
    couverture de données, la file de découverte, le compute."""
    sys.path.insert(0, str(ROOT))
    from scripts.label_matrix import snapshot_id
    now = datetime.now(timezone.utc)
    L = [f"# CONTEXTE DISCOVERY — HEAD {_head()} · {now:%d/%m %H:%M} UTC", "",
         "⚠️ Ce contexte est AVEUGLE à la validation : aucun verdict de",
         "confirmation, aucun score OOS n'y figure (fuite B = contamination).", ""]
    L.append("## Les mécanismes morts (ne pas re-tester sans NOUVEAU mécanisme)")
    dead = _dead_mechanisms()
    L += [f"- {d}" for d in dead] or ["- (aucune famille REJECTED listée)"]
    L.append("")
    L.append("## Les primitives disponibles")
    reg = ROOT / "research" / "features" / "registry.yaml"
    if reg.exists():
        for raw in reg.read_text(encoding="utf-8").splitlines():
            if raw.strip().startswith("- name:"):
                L.append(f"- {raw.split(':')[1].strip()}")
    L.append("")
    try:
        from scripts.label_matrix import KDB
        import sqlite3
        con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
        r = con.execute("SELECT COUNT(*), MIN(open_time), MAX(open_time) "
                        "FROM klines WHERE interval='1h'").fetchone()
        con.close()
        L.append(f"## La couverture de données\n- klines 1h : {r[0]} barres, "
                 f"{datetime.fromtimestamp(r[1]/1000, tz=timezone.utc):%Y-%m-%d} → "
                 f"{datetime.fromtimestamp(r[2]/1000, tz=timezone.utc):%Y-%m-%d} · "
                 f"snapshot {snapshot_id()}")
    except Exception as exc:
        L.append(f"## La couverture de données\n- illisible : {exc}")
    q = ROOT / "research" / "queue"
    if q.exists():
        L.append("")
        L.append("## La file de découverte\n" + "\n".join(
            f"- {f.name}" for f in sorted(q.glob("*.y*ml"))))
    return "\n".join(L)


def confirmation_context(experiment_id: str) -> str:
    """Le contexte CONFIRMATION — la spec gelée et ses critères, RIEN d'autre
    (pas les autres expériences, pas l'historique, pas la découverte)."""
    L = [f"# CONTEXTE CONFIRMATION — {_head()}", "",
         f"Expérience : {experiment_id}",
         "Le protocole est GELÉ : aucun tuning, aucun paramètre, aucun coût.",
         "Le résultat sera SEAL puis VERDICT — le slot est consommé.", ""]
    rdir = RUNS / experiment_id
    for name in ("spec.json", "summary_discovery.json"):
        f = rdir / name
        if f.exists():
            L.append(f"## {name}\n")
            L.append(f.read_text(encoding="utf-8")[:1800])
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Le manifeste de contexte par mode")
    ap.add_argument("--mode", choices=["discovery", "confirmation", "full"],
                    default="full")
    ap.add_argument("--id", help="l'expérience (mode confirmation)")
    a = ap.parse_args()
    if a.mode == "discovery":
        print(discovery_context())
        return 0
    if a.mode == "confirmation":
        if not a.id:
            print("confirmation : --id requis")
            return 2
        print(confirmation_context(a.id))
        return 0
    now = datetime.now(timezone.utc)
    print(f"# CONTEXTE — HEAD {_head()} · généré {now:%d/%m %H:%M} UTC\n")

    # 1. l'état officiel
    if STATE.exists():
        print("## L'état (research/STATE.md)\n")
        print(STATE.read_text(encoding="utf-8").strip()[:2400])
        print()

    # 2. le ledger de preuves
    facts = []
    if LEDGER.exists():
        with open(LEDGER, encoding="utf-8") as f:
            facts = [json.loads(l) for l in f if l.strip()]
    from collections import Counter
    c = Counter(x.get("status", "?") for x in facts)
    print(f"## Le ledger de preuves — {len(facts)} faits "
          f"({', '.join(f'{k} {v}' for k, v in sorted(c.items()))})\n")
    print("Vérifiable via `python scripts/claim_verify.py --all` — un fait")
    print("CONTRADICTED ou UNVERIFIED bloque toute décision.\n")
    print("Les 8 faits les plus récents :")
    for x in facts[-8:]:
        print(f"  {x.get('id')} [{x.get('status')}] {x.get('claim', '')[:96]}…")
    print()

    # 3. le budget
    print(f"## Le budget expérimental\n  {_budget()}\n")

    # 4. les derniers verdicts
    if TRIALS.exists():
        lines = [l for l in TRIALS.read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"## Les {min(3, len(lines))} derniers verdicts\n")
        for l in lines[-3:]:
            try:
                x = json.loads(l)
                print(f"  {x.get('date')} [{x.get('verdict')}] "
                      f"{x.get('family')}/{x.get('strategy')} — "
                      f"{x.get('hypothesis', '')[:80]}")
            except json.JSONDecodeError:
                continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
