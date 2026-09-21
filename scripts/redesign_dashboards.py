#!/usr/bin/env python3
"""Redesign des dashboards legacy Aster dans le design system CE-001.

Pipeline : extraction STRUCTURELLE du contenu de chaque HTML legacy
(titres, tableaux, paragraphes, listes — via le DOM rendu), puis
regeneration dans le template dark premium (navy #0B1220, accents cyan,
tables sombres, cartes), rendu vectoriel A4 pagine.

Contrairement au reskin (qui habillait le vieux HTML), ici le HTML de
sortie est ENTIEREMENT regenere : meme donnees, nouvelle peau.

    python scripts/redesign_dashboards.py "docs/archive/*.html" --delete-source
"""
from __future__ import annotations

import argparse
import html as html_mod
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.html_to_pdf import TITLES  # noqa: E402

REPORTS = ROOT / "reports"
CONVERSION_DATE = "2026-09-21"
EXTRACT_JS = """
() => {
  const blocks = [];
  const walk = (el) => {
    for (const child of el.children) {
      const tag = child.tagName.toLowerCase();
      if (['script', 'style', 'noscript', 'svg'].includes(tag)) continue;
      if (/^h[1-4]$/.test(tag)) {
        const text = child.innerText.trim();
        if (text) blocks.push({ t: 'h', lvl: parseInt(tag[1]), text });
      } else if (tag === 'table') {
        const rows = [...child.querySelectorAll('tr')].map(tr =>
          [...tr.cells].map(td => td.innerText.trim().replace(/\\s+/g, ' '))
        );
        blocks.push({ t: 'table', rows });
      } else if (tag === 'p' || tag === 'blockquote') {
        const text = child.innerText.trim();
        if (text) blocks.push({ t: 'p', text });
      } else if (tag === 'ul' || tag === 'ol') {
        const items = [...child.children]
          .map(li => li.innerText.trim()).filter(Boolean);
        if (items.length) blocks.push({ t: 'ul', items });
      } else if (tag === 'pre') {
        const text = child.innerText.trim();
        if (text) blocks.push({ t: 'pre', text });
      } else if (child.children.length) {
        walk(child);
      } else {
        const text = child.innerText ? child.innerText.trim() : '';
        if (text) blocks.push({ t: 'p', text });
      }
    }
  };
  walk(document.body);
  return { title: document.title, blocks };
}
"""

CSS = """
  @page { size: A4; margin: 11mm 0; }
  html, body {
    margin: 0; padding: 0; background: #0B1220;
    font-family: "Roboto", "Noto Sans", "DejaVu Sans", sans-serif;
    color: #C9D6E8;
  }
  .content { padding: 2mm 14mm 6mm; }
  .cover {
    background: linear-gradient(180deg, #0E1B33 0%, #0B1220 100%);
    border-bottom: 1px solid rgba(56,189,248,.3);
    padding: 14mm 16mm 10mm; margin: -11mm 0 8mm;
  }
  .cover .kicker {
    font-size: 9pt; letter-spacing: 3.5px; color: #38BDF8;
    text-transform: uppercase; font-weight: 700; margin-bottom: 4mm;
  }
  .cover h1 { font-size: 24pt; font-weight: 800; color: #F0F6FC; margin: 0 0 3mm; }
  .cover .meta { font-size: 8.5pt; color: #64748B; }
  h2 {
    font-size: 15pt; font-weight: 800; color: #F0F6FC;
    margin: 9mm 0 3.5mm; padding-bottom: 2mm;
    border-bottom: 2px solid rgba(56,189,248,.35);
    break-after: avoid;
  }
  h3 { font-size: 11.5pt; font-weight: 700; color: #7DD3FC;
       margin: 6mm 0 2.5mm; break-after: avoid; }
  h4 { font-size: 10.5pt; color: #E6EDF3; margin: 4mm 0 2mm; break-after: avoid; }
  p { font-size: 9.5pt; line-height: 1.6; margin: 0 0 3mm;
      overflow-wrap: break-word; }
  ul { margin: 0 0 3mm; padding-left: 5mm; }
  li { font-size: 9.5pt; line-height: 1.55; margin-bottom: 1.5mm;
       overflow-wrap: break-word; }
  pre {
    background: #111A2E; border: 1px solid #1E2A44; border-radius: 6px;
    padding: 4mm; font-size: 8pt; color: #93C5FD;
    overflow-wrap: break-word; white-space: pre-wrap;
    break-inside: avoid; margin: 0 0 3mm;
  }
  table {
    width: 100%; border-collapse: collapse; font-size: 8pt;
    margin: 0 0 4mm; table-layout: fixed;
  }
  th {
    background: #16233D; color: #7DD3FC; text-align: left;
    padding: 2.5mm 3mm; border: 1px solid #1E2A44;
    font-weight: 700; font-size: 7.5pt; text-transform: uppercase;
    letter-spacing: .5px; overflow-wrap: break-word;
  }
  td {
    border: 1px solid #1E2A44; padding: 2.2mm 3mm; color: #C9D6E8;
    overflow-wrap: break-word; vertical-align: top;
  }
  tr:nth-child(even) td { background: #0F1830; }
  tr { break-inside: avoid; }
  .tbl-part {
    font-size: 8pt; color: #38BDF8; font-weight: 700;
    letter-spacing: 1px; margin: 4mm 0 1.5mm;
  }
  .foot {
    margin-top: 10mm; padding-top: 4mm;
    border-top: 1px solid rgba(56,189,248,.2);
    font-size: 7.5pt; color: #64748B;
    display: flex; justify-content: space-between;
  }
"""


def _esc(text: str) -> str:
    return html_mod.escape(text or "")


def _build_html(title: str, blocks: list[dict]) -> str:
    now = _utc_now()
    body: list[str] = []
    body.append(f"""
  <div class="cover">
    <div class="kicker">Core Equity — Archives Aster</div>
    <h1>{_esc(title)}</h1>
    <div class="meta">Dashboard converti et redessiné le {CONVERSION_DATE} —
    recherche-only, pas un signal de trading — généré {_esc(now)} UTC</div>
  </div>""")
    first_h1_done = False
    for b in blocks:
        if b["t"] == "h":
            lvl = b["lvl"]
            text = _esc(b["text"])
            if lvl == 1 and not first_h1_done:
                # le h1 principal est deja dans la couverture
                first_h1_done = True
                continue
            tag = "h2" if lvl <= 2 else ("h3" if lvl == 3 else "h4")
            body.append(f"<{tag}>{text}</{tag}>")
        elif b["t"] == "table":
            rows = b["rows"]
            if not rows:
                continue
            n_cols = max(len(r) for r in rows)
            head = rows[0]
            data = rows[1:]
            if n_cols <= 12:
                body.append("<table>")
                body.append("<tr>" + "".join(f"<th>{_esc(c)}</th>" for c in head) + "</tr>")
                for r in data:
                    cells = list(r) + [""] * (n_cols - len(r))
                    body.append("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in cells) + "</tr>")
                body.append("</table>")
            else:
                # table tres large (30+ colonnes) : decoupage horizontal en
                # blocs de 8 colonnes avec la colonne identifiant repetee —
                # sinon A4 ecrase chaque colonne a 1 caractere de large
                chunk = 8
                n_parts = math.ceil((n_cols - 1) / chunk)
                for part in range(n_parts):
                    cols = [0] + list(range(1 + part * chunk,
                                            min(1 + (part + 1) * chunk, n_cols)))
                    body.append(f'<p class="tbl-part">— partie {part + 1}/{n_parts} —</p>')
                    body.append("<table>")
                    body.append("<tr>" + "".join(
                        f"<th>{_esc(head[c]) if c < len(head) else ''}</th>"
                        for c in cols) + "</tr>")
                    for r in data:
                        cells = [(r[c] if c < len(r) else "") for c in cols]
                        body.append("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in cells) + "</tr>")
                    body.append("</table>")
        elif b["t"] == "p":
            body.append(f"<p>{_esc(b['text'])}</p>")
        elif b["t"] == "ul":
            body.append("<ul>" + "".join(f"<li>{_esc(i)}</li>" for i in b["items"]) + "</ul>")
        elif b["t"] == "pre":
            body.append(f"<pre>{_esc(b['text'])}</pre>")
    body.append(f"""
  <div class="foot">
    <span>Core Equity Research — archive Aster redesignée, lecture seule</span>
    <span>{_esc(now[:10])}</span>
  </div>""")
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>{_esc(title)}</title><style>{CSS}</style></head>
<body><div class="content">{''.join(body)}</div></body></html>"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description="Redesign des dashboards legacy")
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--delete-source", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="traite N fichiers max (debug)")
    args = ap.parse_args()

    files: list[Path] = []
    for pattern in args.patterns:
        p = Path(pattern)
        if p.is_file():
            files.append(p.resolve())
        else:
            files.extend(sorted(ROOT.glob(pattern)))
    files = [f for f in files if f.suffix == ".html"]
    if args.limit:
        files = files[: args.limit]
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
                new_name, out_title = TITLES.get(
                    title_key, (title_key, title_key.replace("-", " ").title())
                )
                page.goto(f.as_uri(), wait_until="load", timeout=30000)
                page.wait_for_timeout(600)
                data = page.evaluate(EXTRACT_JS)
                doc_title = data["title"] or out_title
                html = _build_html(doc_title, data["blocks"])
                out = f.parent / (new_name + ".pdf")
                tmp_html = f.parent / (new_name + ".redesign.html")
                tmp_html.write_text(html, encoding="utf-8")
                page.goto(tmp_html.as_uri(), wait_until="load")
                page.wait_for_timeout(500)
                page.pdf(
                    path=str(out), width="210mm", height="297mm",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
                tmp_html.unlink()
                if args.delete_source:
                    os.remove(f)
                print(f"[redesign] OK {f.name} -> {out.name} "
                      f"({out.stat().st_size // 1024} Ko, {len(data['blocks'])} blocs)")
                ok += 1
            except Exception as exc:
                print(f"[redesign] ECHEC {f.name} : {type(exc).__name__} {exc}",
                      file=sys.stderr)
                failed += 1
        browser.close()
    print(f"[redesign] {ok} redesign, {failed} echecs")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
