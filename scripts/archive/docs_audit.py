#!/usr/bin/env python3
"""Audit de la documentation — anti-proliferation.

Lit le front-matter YAML des docs vivants de docs/ et signale :
  - les docs sans front-matter (non declares)
  - les docs stale (> STALE_DAYS sans mise a jour)
  - les fichiers .md apparus a la racine de docs/ hors liste blanche
  - les snapshots dates qui traineraient dans docs/ au lieu de reports/

Read-only. Ne modifie rien. Exit code 1 si probleme detecte.

Usage:  python scripts/docs_audit.py
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
STALE_DAYS = 90

# Les seuls .md autorises a la racine de docs/
ALLOWED = {
    "README.md",
    "01-onboarding.md",
    "02-architecture.md",
    "03-methodology.md",
    "04-runbook.md",
    "05-data-sources.md",
    "06-data.md",
    "07-backtest-engine.md",
    "08-contributing.md",
    "09-pipeline.md",
    "10-strategies.md",
    "11-campaign-real.md",
    "12-nondirectional.md",
    "13-orchestration.md",
}

# Un doc dont le nom ressemble a une sortie de run n'a rien a faire dans docs/
SNAPSHOT_PATTERNS = [
    r"\d{4}-\d{2}",          # date dans le nom
    r"-report$",
    r"-status$",
    r"-dashboard$",
    r"-snapshot$",
    r"-watchlist$",
    r"-comparison$",
]


def front_matter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta


def main() -> int:
    problems: list[str] = []
    rows: list[tuple[str, str, str, str]] = []
    today = dt.date.today()

    for path in sorted(DOCS.glob("*.md")):
        name = path.name
        stem = path.stem

        if name not in ALLOWED:
            problems.append(
                f"NON DECLARE   {name} — pas dans la liste blanche de docs_audit.py. "
                f"Connaissance durable -> reference/ | perime -> archive/ | "
                f"sortie de run -> reports/"
            )

        for pat in SNAPSHOT_PATTERNS:
            if re.search(pat, stem):
                problems.append(
                    f"SNAPSHOT      {name} — ressemble a une sortie de run. "
                    f"Deplace vers reports/."
                )
                break

        meta = front_matter(path)
        if not meta:
            problems.append(f"SANS ENTETE   {name} — front-matter YAML manquant.")
            rows.append((name, "?", "?", "?"))
            continue

        updated = meta.get("updated", "?")
        flag = ""
        try:
            age = (today - dt.date.fromisoformat(updated)).days
            if age > STALE_DAYS:
                flag = f"STALE ({age}j)"
                problems.append(
                    f"STALE         {name} — pas mis a jour depuis {age} jours."
                )
        except ValueError:
            flag = "date invalide"
            problems.append(f"DATE          {name} — 'updated: {updated}' illisible.")

        rows.append((name, meta.get("status", "?"), updated, flag))

    print(f"Docs vivants dans docs/ : {len(rows)}\n")
    print(f"{'FICHIER':<24} {'STATUS':<9} {'UPDATED':<12} FLAG")
    print("-" * 62)
    for name, status, updated, flag in rows:
        print(f"{name:<24} {status:<9} {updated:<12} {flag}")

    for sub in ("reference", "archive", "security"):
        d = DOCS / sub
        if d.is_dir():
            n = len(list(d.glob("*.md"))) + len(list(d.glob("*.html")))
            print(f"\n{sub+'/':<12} {n} fichiers")

    if problems:
        print(f"\n{len(problems)} probleme(s) :\n")
        for p in problems:
            print("  " + p)
        return 1

    print("\nOK — documentation propre.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
