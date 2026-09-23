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
import re
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
  html, body {
    margin: 0; padding: 0; background: #FFFFFF;
    font-family: "Roboto", "Noto Sans", "DejaVu Sans", sans-serif;
    color: #1E293B;
  }
  .content { padding: 2mm 14mm 0; }
  .cover {
    padding: 6mm 0 7mm; margin-bottom: 9mm;
    border-bottom: 3px solid #0F172A;
  }
  .cover .kicker {
    font-size: 9pt; letter-spacing: 3.5px; color: #0369A1;
    text-transform: uppercase; font-weight: 700; margin-bottom: 4mm;
  }
  .cover h1 { font-size: 25pt; font-weight: 800; color: #0F172A; margin: 0 0 3mm;
              letter-spacing: -0.4px; }
  .cover .meta { font-size: 8.5pt; color: #64748B; }
  h2 {
    font-size: 15.5pt; font-weight: 800; color: #0F172A;
    margin: 10mm 0 3.5mm; padding-bottom: 1.5mm;
    border-bottom: 1px solid #CBD5E1;
    break-after: avoid;
  }
  h3 { font-size: 11.5pt; font-weight: 700; color: #0369A1;
       margin: 6mm 0 2.5mm; break-after: avoid; }
  h4 { font-size: 10.5pt; font-weight: 700; color: #0F172A; margin: 4mm 0 2mm;
       break-after: avoid; }
  p { font-size: 10pt; line-height: 1.65; margin: 0 0 3.5mm; color: #334155;
      overflow-wrap: break-word; }
  ul { margin: 0 0 3.5mm; padding-left: 5mm; }
  li { font-size: 10pt; line-height: 1.6; margin-bottom: 1.6mm; color: #334155; }
  li::marker { color: #0369A1; }
  pre {
    background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px;
    padding: 4mm; font-size: 8pt; color: #0F172A;
    overflow-wrap: break-word; white-space: pre-wrap;
    break-inside: avoid; margin: 0 0 3.5mm;
  }
  table {
    width: 100%; border-collapse: collapse; font-size: 8.5pt;
    margin: 0 0 5mm; table-layout: auto;
  }
  th {
    color: #0F172A; text-align: left;
    border-top: 2px solid #0F172A; border-bottom: 1.2px solid #0F172A;
    padding: 2.5mm 2.8mm; font-weight: 700; font-size: 8pt;
    overflow-wrap: break-word; background: #F8FAFC;
  }
  td {
    border-bottom: 0.75px solid #E2E8F0; padding: 2.2mm 2.8mm; color: #334155;
    vertical-align: top; word-break: normal;
  }
  tr { break-inside: avoid; }
  .tbl-part {
    font-size: 8pt; color: #0369A1; font-weight: 700;
    letter-spacing: 1px; margin: 4mm 0 1.5mm;
  }
  .kv-grid {
    display: flex; flex-wrap: wrap; gap: 3mm;
    margin: 3mm 0 5mm;
  }
  .kv {
    flex: 1 1 42mm; min-width: 36mm; max-width: 70mm;
    background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px;
    padding: 3mm 3.5mm; break-inside: avoid;
  }
  .kv .k {
    font-size: 7.5pt; color: #64748B; text-transform: uppercase;
    letter-spacing: .8px; margin-bottom: 1.2mm;
  }
  .kv .v {
    font-size: 10.5pt; font-weight: 700; color: #0F172A;
    overflow-wrap: break-word;
  }
  .kv .v.small {
    font-size: 8.5pt; font-weight: 600; line-height: 1.45; color: #1E293B;
  }
  .chips { margin: 0 0 4mm; }
  .chip {
    display: inline-block; font-size: 8.5pt; font-weight: 600;
    color: #0369A1; background: #F0F9FF; border: 1px solid #BAE6FD;
    border-radius: 14px; padding: 1.5mm 3.5mm; margin: 0 2mm 2mm 0;
  }
  .doc-meta {
    font-size: 8pt; color: #94A3B8; font-style: italic;
    margin: -4mm 0 6mm;
  }
  .foot {
    margin-top: 12mm; padding-top: 3mm;
    border-top: 1px solid #CBD5E1;
    font-size: 8pt; color: #64748B;
    display: flex; justify-content: space-between;
  }
"""


def _esc(text: str) -> str:
    return html_mod.escape(text or "")


META_RE = None  # compilé paresseusement dans polish()


def _is_labelish(text: str) -> bool:
    """Un paragraphe court, sans ponctuation finale, qui ressemble a une
    etiquette de donnee ('Discovery rows', 'Phase', 'Top lanes')."""
    t = text.strip()
    if not t or len(t) > 60:
        return False
    if t.endswith((".", "!", "?", ":", ";", ",")):
        return False
    if t[0].isdigit():
        return False
    return len(t.split()) <= 6


def _is_valueish(text: str) -> bool:
    t = text.strip()
    return bool(t) and len(t) <= 120 and not t.endswith((".", "!", "?"))


def polish(blocks: list[dict]) -> list[dict]:
    """Couche editoriale : transforme le dump DOM en document organise.

    - etiquettes + valeurs consecutives -> groupes KPI (cartes)
    - listes a barres 'a | b | c' -> chips
    - metadonnees de generation -> note discrete de couverture
    """
    out: list[dict] = []
    meta_lines: list[str] = []
    meta_re = re.compile(r"^(generation|généré|genere)\b", re.I)
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b["t"] == "p":
            text = b["text"].strip()
            if meta_re.match(text):
                meta_lines.append(text)
                i += 1
                continue
            if _is_labelish(text) and i + 1 < len(blocks) \
                    and blocks[i + 1]["t"] == "p" \
                    and _is_valueish(blocks[i + 1]["text"]):
                # chaine etiquette -> valeur (-> etiquette -> valeur ...)
                pairs: list[tuple[str, str]] = []
                label = text
                j = i + 1
                while j < len(blocks) and blocks[j]["t"] == "p" \
                        and _is_valueish(blocks[j]["text"]):
                    pairs.append((label, blocks[j]["text"].strip()))
                    j += 1
                    if j < len(blocks) and blocks[j]["t"] == "p" \
                            and _is_labelish(blocks[j]["text"]):
                        label = blocks[j]["text"].strip()
                        j += 1
                    else:
                        break
                out.append({"t": "kv", "items": pairs})
                i = j
                continue
            # marqueur de liste aplati par le legacy ("4" seul) -> jete
            if re.fullmatch(r"\d{1,2}", text) and i + 1 < len(blocks) \
                    and blocks[i + 1]["t"] == "p" \
                    and _is_labelish(blocks[i + 1]["text"]):
                i += 1
                continue
            # liste a barres -> chips (sans plafond : les listes de symboles
            # de 15+ elements doivent devenir des chips, pas du CSV cru)
            if "|" in text and text.count("|") >= 2 and len(text) < 400:
                parts = [p.strip() for p in text.split("|") if p.strip()]
                out.append({"t": "chips", "items": parts})
                i += 1
                continue
            # liste de tickers a virgules (tout caps, sans espaces)
            if re.fullmatch(r"[A-Z0-9,]+", text) and text.count(",") >= 3:
                parts = [p.strip() for p in text.split(",") if p.strip()]
                out.append({"t": "chips", "items": parts})
                i += 1
                continue
                parts = [p.strip() for p in text.split("|") if p.strip()]
                out.append({"t": "chips", "items": parts})
                i += 1
                continue
        out.append(b)
        i += 1
    if meta_lines:
        out.insert(0, {"t": "meta", "lines": meta_lines})
    return out


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
                body.append("<table><thead><tr>"
                            + "".join(f"<th>{_esc(c)}</th>" for c in head)
                            + "</tr></thead><tbody>")
                for r in data:
                    cells = list(r) + [""] * (n_cols - len(r))
                    body.append("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in cells) + "</tr>")
                body.append("</tbody></table>")
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
                    body.append("<table><thead><tr>" + "".join(
                        f"<th>{_esc(head[c]) if c < len(head) else ''}</th>"
                        for c in cols) + "</tr></thead><tbody>")
                    for r in data:
                        cells = [(r[c] if c < len(r) else "") for c in cols]
                        body.append("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in cells) + "</tr>")
                    body.append("</tbody></table>")
        elif b["t"] == "kv":
            body.append('<div class="kv-grid">')
            for label, value in b["items"]:
                vclass = "v" if len(value) <= 50 else "v small"
                body.append(
                    f'<div class="kv"><div class="k">{_esc(label)}</div>'
                    f'<div class="{vclass}">{_esc(value)}</div></div>'
                )
            body.append("</div>")
        elif b["t"] == "chips":
            body.append('<div class="chips">' + "".join(
                f'<span class="chip">{_esc(c)}</span>' for c in b["items"]) + "</div>")
        elif b["t"] == "meta":
            body.append('<div class="doc-meta">'
                        + "<br>".join(_esc(l) for l in b["lines"]) + "</div>")
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
                blocks = polish(data["blocks"])
                doc_title = out_title or data["title"] or title_key
                html = _build_html(doc_title, blocks)
                out = f.parent / (new_name + ".pdf")
                tmp_html = f.parent / (new_name + ".redesign.html")
                tmp_html.write_text(html, encoding="utf-8")
                page.goto(tmp_html.as_uri(), wait_until="load")
                page.wait_for_timeout(500)
                page.pdf(
                    path=str(out), width="210mm", height="297mm",
                    print_background=True,
                    display_header_footer=True,
                    header_template=(
                        '<div style="width:100%; font-size:7px; padding:0 14mm; '
                        'color:#94A3B8;">Core Equity — ' + _esc(out_title) + "</div>"
                    ),
                    footer_template=(
                        '<div style="width:100%; font-size:7px; padding:0 14mm; '
                        'color:#94A3B8;"><span style="float:left">Core Equity '
                        'Research</span><span style="float:right">page '
                        '<span class="pageNumber"></span> / '
                        '<span class="totalPages"></span></span></div>'
                    ),
                    margin={"top": "15mm", "bottom": "13mm",
                            "left": "0", "right": "0"},
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
