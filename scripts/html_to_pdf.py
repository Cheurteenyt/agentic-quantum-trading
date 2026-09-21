#!/usr/bin/env python3
"""Conversion batch HTML -> PDF vectoriel (Chromium headless via patchright).

Concu pour les dashboards HTML auto-generes (cockpits Aster, truth reports...)
: chaque PDF est dimensionne a la TAILLE REELLE du contenu (scrollWidth x
scrollHeight), ce qui preserve exactement la mise en page au lieu de la
decouper en pages A4.

    python scripts/html_to_pdf.py "docs/archive/*.html"
    python scripts/html_to_pdf.py "reports/registre-board.html" --output-suffix ""

Sortie : meme dossier que le fichier source, meme basename en .pdf.
Un fichier qui echoue est logge et saute (le batch continue).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTLE_MS = 700


def convert(page, html_path: Path) -> Path | None:
    page.goto(html_path.as_uri(), wait_until="load", timeout=30000)
    page.wait_for_timeout(SETTLE_MS)
    width = page.evaluate("Math.max(document.documentElement.scrollWidth, 1280)")
    height = page.evaluate("Math.max(document.documentElement.scrollHeight, 800)")
    out = html_path.with_suffix(".pdf")
    page.pdf(
        path=str(out),
        width=f"{width}px",
        height=f"{height + 4}px",
        print_background=True,
        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="HTML -> PDF batch (vectoriel)")
    ap.add_argument("patterns", nargs="+", help="chemins ou globs de fichiers HTML")
    args = ap.parse_args()

    files: list[Path] = []
    for pattern in args.patterns:
        if Path(pattern).is_file():
            files.append(Path(pattern))
        else:
            files.extend(sorted(ROOT.glob(pattern)))
    files = [f for f in files if f.suffix == ".html"]
    if not files:
        print("aucun fichier HTML matching", file=sys.stderr)
        return 1

    from patchright.sync_api import sync_playwright

    ok = failed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for f in files:
            try:
                out = convert(page, f)
                size = out.stat().st_size if out else 0
                print(f"[html2pdf] OK    {f.name} -> {out.name} ({size // 1024} Ko)")
                ok += 1
            except Exception as exc:
                print(f"[html2pdf] ECHEC {f.name} : {type(exc).__name__} {exc}",
                      file=sys.stderr)
                failed += 1
        browser.close()
    print(f"[html2pdf] {ok} convertis, {failed} echecs")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
