#!/usr/bin/env python3
"""Conversion batch HTML -> PDF vectoriel avec RESKIN design unifie.

Concu pour les dashboards HTML auto-generes (archives Aster...). Deux modes :

  par defaut : capture fidele, PDF dimensionne a la taille reelle du contenu.
  --reskin   : injection d'un design system premium (bandeau de marque,
               typographie Roboto/Noto Sans, tables stylees, fond blanc
               lisible) AVANT le rendu — les couleurs metier des cellules
               sont preservees, seule l'enveloppe est unifiee.

Titres/metadonnees : TITLES (cle = basename) — noms francais lisibles.

    python scripts/html_to_pdf.py "docs/archive/*.html" --reskin --delete-source
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTLE_MS = 700
CONVERSION_DATE = "2026-09-21"

TITLES: dict[str, str] = {
    "core-equity-aster-research-consolidated-report": ("aster-cockpit-consolide", "Aster — Cockpit consolidé de recherche"),
    "core-equity-aster-code-map": ("aster-carte-du-code", "Aster — Carte du code"),
    "core-equity-aster-strategy-registry": ("aster-registre-des-strategies", "Aster — Registre des stratégies"),
    "core-equity-aster-strategy-truth-report": ("aster-rapport-de-verite-strategies", "Aster — Rapport de vérité (stratégies)"),
    "core-equity-aster-promotion-truth-report": ("aster-rapport-de-verite-promotion", "Aster — Rapport de vérité (promotion)"),
    "core-equity-aster-lane-promotion-scoring": ("aster-scoring-des-lanes", "Aster — Scoring de promotion des lanes"),
    "core-equity-aster-promotion-ready-lanes": ("aster-lanes-pretes-a-la-promotion", "Aster — Lanes prêtes à la promotion"),
    "core-equity-aster-candidate-validation-queue": ("aster-file-de-validation-candidats", "Aster — File de validation des candidats"),
    "core-equity-aster-queue-reality-pack-validator": ("aster-validateur-reality-pack", "Aster — Validateur reality pack"),
    "core-equity-aster-current-state": ("aster-etat-actuel", "Aster — État actuel"),
    "core-equity-aster-documentation-hub": ("aster-hub-de-documentation", "Aster — Hub de documentation"),
    "core-equity-aster-workspace-file-audit": ("aster-audit-des-fichiers", "Aster — Audit des fichiers du workspace"),
    "core-equity-aster-workspace-artifact-archive-plan": ("aster-plan-darchivage-des-artefacts", "Aster — Plan d'archivage des artefacts"),
    "core-equity-aster-artifact-value-map": ("aster-carte-de-valeur-des-artefacts", "Aster — Carte de valeur des artefacts"),
    "core-equity-aster-asset-strategy-recommendations": ("aster-recommandations-par-actif", "Aster — Recommandations par actif"),
    "core-equity-aster-volatile-crypto-discovery": ("aster-decouverte-des-cryptos-volatiles", "Aster — Découverte des cryptos volatiles"),
    "core-equity-aster-rl-lane-policy": ("aster-politique-rl-des-lanes", "Aster — Politique RL des lanes"),
    "core-equity-aster-research-report": ("aster-rapport-de-recherche", "Aster — Rapport de recherche"),
    "core-equity-null-results-report": ("carte-des-resultats-nuls", "Carte des résultats nuls (toutes stratégies)"),
    "core-equity-rag-dashboard": ("dashboard-rag", "Dashboard RAG"),
}

RESKIN_CSS = """
<style id="reskin-core-equity">
  body {
    background: #FFFFFF !important;
    color: #0F172A !important;
    font-family: "Roboto", "Noto Sans", "DejaVu Sans", sans-serif !important;
    margin: 0 !important; padding: 0 !important;
  }
  .reskin-head {
    background: #0F172A; color: #F8FAFC;
    padding: 30px 40px; margin: 0 0 28px;
  }
  .reskin-head .k {
    font-size: 11px; letter-spacing: 3px; color: #7DD3FC;
    text-transform: uppercase; margin-bottom: 7px; font-weight: 700;
  }
  .reskin-head .t { font-size: 26px; font-weight: 800; }
  .reskin-head .m { font-size: 11px; color: #94A3B8; margin-top: 8px; }
  .reskin-foot {
    background: #0F172A; color: #94A3B8; font-size: 10px;
    padding: 14px 40px; margin-top: 30px;
    display: flex; justify-content: space-between;
  }
  h1, h2, h3 { color: #0F172A !important; font-weight: 700 !important; }
  h1 { font-size: 24px !important; }
  h2 { font-size: 18px !important; border-bottom: 2px solid #E2E8F0 !important;
       padding-bottom: 6px !important; }
  table { border-collapse: collapse !important; margin: 14px 0 !important;
          font-size: 13px !important; }
  th {
    background: #0F172A !important; color: #F8FAFC !important;
    border: 1px solid #334155 !important; padding: 8px 12px !important;
    text-align: left !important; font-weight: 600 !important;
  }
  td { border: 1px solid #E2E8F0 !important; padding: 7px 12px !important; }
  .reskin-body-pad td, .reskin-body-pad span, .reskin-body-pad div,
  .reskin-body-pad p { color: #0F172A !important; }
  .reskin-body-pad tr:nth-child(even) td { background: #F8FAFC !important; }
  p, li { line-height: 1.55 !important; }
  a { color: #0369A1 !important; }
  pre, code { background: #F1F5F9 !important; color: #0F172A !important; }
  .reskin-body-pad { padding: 0 40px 10px; }
</style>
"""


def _reskin(page, title: str) -> None:
    # STRIP AGRESSIF d'abord : les dashboards legacy portent leurs propres
    # styles (inline + <style>) qui resistent a l'injection — on les retire
    # tous pour que le design system s'applique a 100 %. Le contenu
    # (tables, titres, texte) reste intact.
    page.evaluate(
        """() => {
            document.querySelectorAll('style, link[rel=stylesheet], script')
                .forEach(e => e.remove());
            document.querySelectorAll('[style]')
                .forEach(e => e.removeAttribute('style'));
            document.querySelectorAll('[bgcolor], [background]')
                .forEach(e => { e.removeAttribute('bgcolor');
                                e.removeAttribute('background'); });
            document.querySelectorAll('table')
                .forEach(t => { t.removeAttribute('border');
                                t.removeAttribute('cellpadding');
                                t.removeAttribute('cellspacing');
                                t.removeAttribute('width'); });
            document.querySelectorAll('font').forEach(f => {
                const span = document.createElement('span');
                span.innerHTML = f.innerHTML;
                f.replaceWith(span);
            });
        }"""
    )
    page.add_style_tag(content=RESKIN_CSS)
    page.evaluate(
        """(args) => {
            const { title, stem } = args;
            const head = document.createElement('div');
            head.className = 'reskin-head';
            head.innerHTML = `
                <div class="k">Core Equity — Archives Aster</div>
                <div class="t">${title}</div>
                <div class="m">Dashboard converti en PDF le 2026-09-21 —
                recherche-only, pas un signal de trading</div>`;
            document.body.insertBefore(head, document.body.firstChild);
            const wrapper = document.createElement('div');
            wrapper.className = 'reskin-body-pad';
            const skip = new Set([head]);
            const nodes = [...document.body.children].filter(n => !skip.has(n));
            nodes.forEach(n => wrapper.appendChild(n));
            document.body.appendChild(wrapper);
            // le legacy commence souvent par son propre <h1> qui duplique
            // le titre : on le retire uniquement s'il colle au stem/titre
            const firstH = wrapper.querySelector('h1, h2');
            if (firstH) {
                const t = (firstH.textContent || '');
                if ((stem && t.includes(stem)) || t.includes('.pdf')) firstH.remove();
            }
            const foot = document.createElement('div');
            foot.className = 'reskin-foot';
            foot.innerHTML = `<span>Core Equity Research — archive horodatee,
                lecture seule</span><span>${new Date().toISOString().slice(0, 10)}</span>`;
            document.body.appendChild(foot);
        }""",
        {"title": title, "stem": ""},
    )


def convert(page, html_path: Path, reskin: bool, out_path: Path) -> Path | None:
    page.goto(html_path.as_uri(), wait_until="load", timeout=30000)
    page.wait_for_timeout(SETTLE_MS)
    title_key = html_path.stem
    title = TITLES[title_key][1] if title_key in TITLES \
        else title_key.replace("-", " ").title()
    if reskin:
        _reskin(page, title)
    page.wait_for_timeout(SETTLE_MS)
    width = page.evaluate("Math.max(document.documentElement.scrollWidth, 1280)")
    height = page.evaluate("Math.max(document.documentElement.scrollHeight, 800)")
    page.pdf(
        path=str(out_path),
        width=f"{width}px",
        height=f"{height + 4}px",
        print_background=True,
        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
    )
    return out_path


def _set_metadata(pdf_path: Path, title: str) -> None:
    from pypdf import PdfReader, PdfWriter

    r = PdfReader(str(pdf_path))
    w = PdfWriter()
    for pg in r.pages:
        w.add_page(pg)
    w.add_metadata({
        "/Title": title,
        "/Author": "Core Equity Research",
        "/Subject": f"Dashboard Aster — archive convertie en PDF le {CONVERSION_DATE}",
        "/Creator": "Registre pipeline (HTML → vector PDF)",
    })
    with open(pdf_path, "wb") as f:
        w.write(f)


def main() -> int:
    ap = argparse.ArgumentParser(description="HTML -> PDF batch (vectoriel + reskin)")
    ap.add_argument("patterns", nargs="+", help="chemins ou globs de fichiers HTML")
    ap.add_argument("--reskin", action="store_true",
                    help="injecte le design system Core Equity avant rendu")
    ap.add_argument("--delete-source", action="store_true",
                    help="supprime le HTML source apres conversion reussie")
    args = ap.parse_args()

    files: list[Path] = []
    for pattern in args.patterns:
        p = Path(pattern)
        if p.is_file():
            files.append(p.resolve())
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
                title_key = f.stem
                title = TITLES[title_key][1] if title_key in TITLES \
                    else title_key.replace("-", " ").title()
                out_name = (TITLES[title_key][0] + ".pdf") if title_key in TITLES \
                    else None
                out = convert(page, f, args.reskin,
                              f.parent / out_name if out_name else f.with_suffix(".pdf"))
                _set_metadata(out, title)
                if args.delete_source:
                    os.remove(f)
                print(f"[html2pdf] OK    {f.name} -> {out.name} ({out.stat().st_size // 1024} Ko)")
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
