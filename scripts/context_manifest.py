#!/usr/bin/env python
"""LE MANIFESTE DE CONTEXTE — Research Firewall, couche 2 (audit GPT v3 §26).

Le brief d'entrée d'une session : HEAD, l'état officiel (STATE.md), les faits
du ledger (research/evidence/facts.jsonl), l'état du budget, les derniers
verdicts. Une session lit CE manifeste au lieu de relire 127 Ko de registre —
et tout ce qu'il contient est vérifiable via scripts/claim_verify.py.

    python scripts/context_manifest.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "research" / "evidence" / "facts.jsonl"
STATE = ROOT / "research" / "STATE.md"
TRIALS = ROOT / "research" / "ledger" / "trials.jsonl"


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


def main() -> int:
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
