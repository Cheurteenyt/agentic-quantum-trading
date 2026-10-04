#!/usr/bin/env python
"""LE VÉRIFICATEUR DE PREUVES — Research Firewall, couche 4 (audit GPT v3 §26).

Chaque fait du ledger (research/evidence/facts.jsonl) est revérifié contre le
code ACTUEL, mécaniquement — jamais sur la foi d'un souvenir de contexte.

Verdicts par fait :
  SUPPORTED    le fait tient : chaque pattern requis est présent, chaque
               pattern interdit est absent
  CONTRADICTED le code contredit le fait (un bug marqué corrigé est
               réapparu, un code marqué mort est revenu)
  UNVERIFIED   invérifiable (fichier manquant, ledger illisible) — et un
               fait UNVERIFIED n'entre jamais dans STATE.md

Champs d'un fait : id, date, sha (le HEAD au moment du constat — informatif,
la vérification est CONTENT-based), path, claim, status (fixed / confirmed /
refuted / stale), require_present, require_absent, evidence, source.

Usage :
  python scripts/claim_verify.py --all           # revérifie tout le ledger
  python scripts/claim_verify.py --id F-001      # un seul fait
  python scripts/claim_verify.py --stats         # comptage par statut
  python scripts/claim_verify.py --add           # squelette d'un nouveau fait

Exit 0 si aucun CONTRADICTED/UNVERIFIED, 1 sinon (branchable en CI).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "research" / "evidence" / "facts.jsonl"

VALID_STATUS = ("fixed", "confirmed", "refuted", "stale", "context")


def _head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()
    except Exception:
        return "?"


def load_ledger(path: Path = LEDGER) -> list[dict]:
    facts = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                facts.append(json.loads(line))
            except json.JSONDecodeError as exc:
                facts.append({"id": f"LIGNE-{n}", "status": "UNVERIFIED",
                              "path": str(path), "claim": f"JSONL illisible: {exc}"})
    return facts


def verify(fact: dict, base: Path = ROOT) -> dict:
    """Revérifie UN fait contre le code actuel. Ne juge pas, mesure.

    `base` est injectable pour les tests (un fixture temporaire)."""
    res = dict(fact)
    path = base / fact.get("path", "")
    if not path.exists():
        res["verdict"] = "UNVERIFIED"
        res["reason"] = f"fichier introuvable: {fact.get('path')}"
        return res
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        res["verdict"] = "UNVERIFIED"
        res["reason"] = f"lecture impossible: {exc}"
        return res

    problems = []
    for pat in fact.get("require_present", []):
        if pat not in content:
            problems.append(f"requis absent: {pat!r}")
    for pat in fact.get("require_absent", []):
        if pat in content:
            problems.append(f"interdit PRÉSENT: {pat!r}")

    if problems:
        res["verdict"] = "CONTRADICTED"
        res["reason"] = " ; ".join(problems)
        return res

    res["verdict"] = "SUPPORTED"
    head = _head()
    if fact.get("sha") and fact["sha"] != head:
        res["frozen_at"] = fact["sha"]
        res["note"] = f"constat gelé à {fact['sha']}, HEAD={head} (vérifié sur le contenu)"
    if fact.get("status") not in VALID_STATUS:
        res["note"] = f"status inconnu: {fact.get('status')!r}"
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Le vérificateur de preuves")
    ap.add_argument("--all", action="store_true", help="revérifie tout le ledger")
    ap.add_argument("--id", help="un seul fait par identifiant")
    ap.add_argument("--stats", action="store_true", help="comptage par statut")
    ap.add_argument("--ledger", default=str(LEDGER))
    args = ap.parse_args()

    facts = load_ledger(Path(args.ledger))
    if not facts:
        print(f"ledger vide ou illisible: {args.ledger}")
        return 1

    if args.stats:
        from collections import Counter
        c = Counter(x.get("status", "?") for x in facts)
        for k, v in sorted(c.items()):
            print(f"  {k:10} {v}")
        return 0

    targets = facts
    if args.id:
        targets = [x for x in facts if x.get("id") == args.id]
        if not targets:
            print(f"fait introuvable: {args.id}")
            return 1

    bad = 0
    for fact in targets:
        res = verify(fact)
        mark = {"SUPPORTED": "OK ", "CONTRADICTED": "!! ", "UNVERIFIED": "?? "}.get(
            res["verdict"], "   ")
        note = f" — {res['note']}" if res.get("note") else ""
        reason = f" — {res['reason']}" if res.get("reason") else ""
        print(f"[{mark}{res['verdict']:12}] {res.get('id', '?'):8} "
              f"{res.get('path', '')}{reason}{note}")
        if res["verdict"] in ("CONTRADICTED", "UNVERIFIED"):
            bad += 1

    total = len(targets)
    print(f"\n{total - bad}/{total} SUPPORTED — "
          f"{'LE LEDGER TIENT' if bad == 0 else 'LE LEDGER EST CONTREDIT : ne rien '
          f'décider sur un fait contredit'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
