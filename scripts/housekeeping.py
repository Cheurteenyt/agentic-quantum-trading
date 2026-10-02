#!/usr/bin/env python
"""Ménage automatique + tableau de bord d'état — la propreté n'est pas optionnelle.

Deux missions (étape nocturne 22) :
1. RÉTENTION : les familles de rapports datés s'accumulent sans limite
   (preuve : 20 logs de campagne dont l'ère WSL, 13 versions du même PDF).
   Chaque famille a un nombre à garder (les plus récents) ; le reste part.
   Les fichiers d'identité (CE-001, drafts, README) ne sont JAMAIS touchés.
2. ÉTAT : reports/etat-projet.md réécrit chaque nuit — services, compteurs
   d'accumulation, tailles, prochain tirage, décisions en attente. Une page
   de faits contre les impressions.

Usage :
  .venv/bin/python scripts/housekeeping.py            # dry-run (ne supprime rien)
  .venv/bin/python scripts/housekeeping.py --apply    # réel (campagne nocturne)
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DB = ROOT / "data" / "warehouse" / "klines.db"
DEPTH_DB = ROOT / "data" / "warehouse" / "depth.db"
X_DB = ROOT / "data" / "warehouse" / "x_posts.db"

# famille (glob) -> combien de plus récents garder. Touche UNIQUEMENT ces motifs.
FAMILIES: list[tuple[str, int]] = [
    ("campaign-nightly-*.md", 5),
    ("registre-honnetete-*.md", 3),
    ("registre-board-*.pdf", 3),
    ("carry-hedged-*.md", 2),
    ("carry-intra-aster-*.md", 2),
    ("funding-scanner-*.md", 2),
    ("depth-heatmap-*.pdf", 9),
    # familles ajoutées le 24/09 (nouvelle pile fomo/X/convergence/backtests)
    ("whale-radar-*.md", 7),
    ("x-aster-pulse-*.md", 7),
    ("aster-convergence-*.md", 7),
    ("memecoin-pulse-*.md", 3),
    ("wave-detector-*.md", 5),
    ("absorption-backtest-*.md", 2),
    ("backtest-campagne-*.md", 5),
    ("backtest-indicators-*.md", 5),
]

PROTECTED = re.compile(r"(ce001|ce-001|thread|draft|README|source_snapshot)", re.IGNORECASE)


def dated_files(pattern: str) -> list[Path]:
    """Fichiers d'une famille, du plus récent au plus ancien (mtime)."""
    files = list(REPORTS.glob(pattern))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def prune(apply: bool) -> list[tuple[Path, str]]:
    """Retourne la liste (chemin, action) des suppressions décidées."""
    actions: list[tuple[Path, str]] = []
    for pattern, keep in FAMILIES:
        files = dated_files(pattern)
        for old in files[keep:]:
            if PROTECTED.search(old.name):
                continue
            actions.append((old, "delete"))
    # HTML résiduel : supprimé seulement si son PDF jumeau existe déjà
    for html in REPORTS.glob("*.html"):
        pdfs = list(REPORTS.glob(html.stem + "*.pdf"))
        if pdfs:
            newest_pdf = max(pdfs, key=lambda p: p.stat().st_mtime)
            if newest_pdf.stat().st_mtime >= html.stat().st_mtime:
                actions.append((html, "delete (pdf plus récent présent)"))
    if not apply:
        return actions
    for path, why in actions:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT))],
            capture_output=True, cwd=ROOT,
        ).returncode == 0
        if tracked:
            subprocess.run(["git", "rm", "-q", "--cached", str(path.relative_to(ROOT))],
                           cwd=ROOT, check=True)
        path.unlink(missing_ok=True)
        print(f"[housekeeping] - {path.name} ({why})")
    return actions


def _count(db: Path, sql: str) -> str:
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
        try:
            (n,) = con.execute(sql).fetchone()
            return f"{n:,}"
        finally:
            con.close()
    except Exception:
        return "—"


def _svc(name: str) -> str:
    r = subprocess.run(["systemctl", "--user", "is-active", name],
                       capture_output=True, text=True)
    return r.stdout.strip() or "inconnu"


def _next_fire() -> str:
    r = subprocess.run(["systemctl", "--user", "list-timers", "trading-agent-nightly.timer",
                        "--no-pager"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if "trading-agent-nightly.timer" in line and "NEXT" not in line:
            return line.split()[0] + " " + line.split()[1]
    return "—"


def write_etat() -> Path:
    def size_of(p: Path) -> str:
        try:
            mb = p.stat().st_size / 1e6
            return f"{mb:,.1f} Mo"
        except OSError:
            return "absent"

    lines = [
        f"# État du projet — {datetime.now(tz=timezone.utc):%d/%m/%Y %H:%M} UTC",
        "",
        "## Ce qui tourne",
        f"- capteur liquidations `aster-liq-collector` : **{_svc('aster-liq-collector.service')}**",
        f"- capteur profondeur `aster-depth-collector` : **{_svc('aster-depth-collector.service')}**",
        f"- campagne nocturne : prochain tirage **{_next_fire()}**",
        "",
        "## Accumulation (la matière première des futurs backtests)",
        f"- flux (absorption/sweep) `flow_events` : {_count(DB, 'SELECT COUNT(*) FROM flow_events')} événements",
        f"- positioning `flow_snapshots` : {_count(DB, 'SELECT COUNT(*) FROM flow_snapshots')} snapshots",
        f"- basis Aster↔Binance : {_count(DB, 'SELECT COUNT(*) FROM basis_snapshots')} mesures",
        f"- liquidations `liq_events` : {_count(DB, 'SELECT COUNT(*) FROM liq_events')} événements",
        f"- registre X : {_count(X_DB, 'SELECT COUNT(*) FROM x_posts')} posts, "
        f"{_count(X_DB, 'SELECT COUNT(*) FROM x_calls')} calls, "
        f"{_count(X_DB, 'SELECT COUNT(*) FROM x_call_verdicts')} verdicts",
        f"- profondeur `depth_bins` : {_count(DEPTH_DB, 'SELECT COUNT(*) FROM depth_bins')} lignes",
        "",
        "## Entrepôts",
        f"- klines.db {size_of(DB)} · depth.db {size_of(DEPTH_DB)} · lab refermé (archive zstd) "
        f"{size_of(ROOT / 'data' / 'warehouse' / 'archive' / 'backtest.db.zst')}",
        "",
        "## Décisions en attente de l'utilisateur",
        "- publier CE-001 (thread prêt, PDF v2 finalisé)",
        "- (après 2-4 semaines d'accumulation) backtest des couches flow/positioning",
        "",
    ]
    out = REPORTS / "etat-projet.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Rétention des rapports + état du projet")
    p.add_argument("--apply", action="store_true", help="supprimer réellement (sinon dry-run)")
    args = p.parse_args()
    actions = prune(args.apply)
    if not args.apply:
        for path, why in actions:
            print(f"[dry-run] - {path.name} ({why})")
        if not actions:
            print("[dry-run] rien à supprimer")
    etat = write_etat()
    print(f"[etat] {etat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
