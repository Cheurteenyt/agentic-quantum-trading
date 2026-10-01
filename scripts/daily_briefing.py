#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LE BRIEFING MATINAL — une page unique, obligatoire (feedback user 01/10).

Agrège en lecture seule (fail-open partout : une source absente n'empêche
jamais le reste) :
  - le forward paper des survivants (ledger aster_survivors_paper, klines.db ro)
  - le dernier rapport de la machine nocturne (reports/the-machine-*.md)
  - la santé des sondes (data/warehouse/aster_health_state.json)
  - les timers 24/7 (systemctl --user list-timers)
  - les derniers rapports toutes domaines (reports/, reports/openmarket/)
  - les tirs à venir (bloc statique — mis à jour à chaque verdict, cf. la
    CARTE DES FRONTS dans Ariad/Obsidian)

Sortie : reports/briefing/briefing-YYYY-MM-DD.md + echo console.
Timer : trading-agent-briefing.timer (07:10 quotidien, après le nocturne 03:00
et le tir forward 06:55).

Usage : .venv/bin/python scripts/daily_briefing.py
"""
import datetime as dt
import glob
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KLINE_DB = ROOT / "data" / "warehouse" / "klines.db"
HEALTH = ROOT / "data" / "warehouse" / "aster_health_state.json"
OUT_DIR = ROOT / "reports" / "briefing"

TIRS_A_VENIR = """
| Tir | Date | Statut |
|---|---|---|
| Forward paper survivants (4 stratégies) | tir quotidien 06:55, verdict ~90 j (janv. 2027) | EN COURS |
| Tirs d'octobre : murs 14 j, OI H4/H5, depth, whaleflow, sonde P3 | 06-08/10 | ARMÉ |
| derek518 réplication passive (fomo) | verdict à ≥ 5 CLOSED | EN ATTENTE |
| bonding n≥60 (fomo) | ~08-09/10 | EN COURS |
| vol_spike promotion | après ~30 trades forward | EN ATTENTE |
| Gate fund7 90 j | activation = décision user | EN ATTENTE |

Décisions user ouvertes : OpenMarket MC v20 (642 $) vs v30 (117 $, P(50100)≈0 %) ·
flux meme ×0 vs ×0,5 · phase 2 (pont fomo→Aster, définition à fixer) · A/B kScripts
(file RI → MK6 → TRAIL → ABS, CSV attendus dans ab/).
""".strip()


def sec(title):
    print(f"\n## {title}\n")
    return None  # helper visuel console


def survivors_forward():
    lines = []
    try:
        con = sqlite3.connect(f"file:{KLINE_DB}?mode=ro", uri=True)
        meta = dict(con.execute("SELECT * FROM aster_survivors_meta").fetchall() or {})
        rows = con.execute(
            "SELECT * FROM aster_survivors_paper ORDER BY rowid DESC LIMIT 8").fetchall()
        cols = [d[0] for d in con.execute("SELECT * FROM aster_survivors_paper LIMIT 1").description]
        n = con.execute("SELECT COUNT(*) FROM aster_survivors_paper").fetchone()[0]
        con.close()
        started = meta.get("started_ms")
        start_txt = (dt.datetime.fromtimestamp(int(started) / 1000).strftime("%F %H:%M")
                     if started else "?")
        lines.append(f"- Ledger : **{n} ligne(s)** · watermark (anti-historique) posé le {start_txt} UTC")
        last = meta.get("last_run_epoch")
        if last:
            lines.append(f"- Dernier tir : {dt.datetime.fromtimestamp(int(last)).strftime('%F %H:%M')}")
        if rows:
            lines.append("")
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("|" + "---|" * len(cols))
            for r in rows:
                lines.append("| " + " | ".join(str(x) for x in r) + " |")
        else:
            lines.append("- Aucune position ouverte/fermée pour l'instant (les signaux légitimes "
                         "n'ont pas encore tiré — le verdict out-of-sample se construit à 90 j).")
    except Exception as e:
        lines.append(f"- (source indisponible : {e})")
    return "\n".join(lines)


def machine_nocturne():
    # le tracker quotidien = reports/paper-forward-*.md (les candidats jugés sur
    # données fraîches à chaque passe) ; the-machine-*.md = les runs manuels.
    pf = sorted(glob.glob(str(ROOT / "reports" / "paper-forward-*.md")), reverse=True)
    files = pf or sorted(glob.glob(str(ROOT / "reports" / "the-machine-*.md")), reverse=True)
    if not files:
        return "- (aucun rapport machine trouvé)"
    latest = files[0]
    name = Path(latest).name
    lines = [f"- Dernier tracker : [`{name}`](./{name}) "
             f"({dt.datetime.fromtimestamp(Path(latest).stat().st_mtime).strftime('%F %H:%M')})"]
    try:
        head = [l.rstrip() for l in open(latest, encoding="utf-8") if l.strip()][:4]
        lines += [f"  > {l}" for l in head[1:4]]
        src = [l.rstrip() for l in open(latest, encoding="utf-8")]
        rows = [l for l in src if l.startswith("|")][:8]
        if rows:
            lines.append("")
            lines += rows
    except Exception:
        pass
    return "\n".join(lines)


def health():
    try:
        st = json.load(open(HEALTH, encoding="utf-8"))
        checks = st.get("checks", st) if isinstance(st, dict) else {}
        if isinstance(checks, dict) and checks:
            oks = [v for v in checks.values()
                   if isinstance(v, dict) and v.get("ok")]
            total = len(checks)
            lines = [f"- Sondes : **{len(oks)}/{total} OK**"]
            bad = {k: v for k, v in checks.items()
                   if isinstance(v, dict) and not v.get("ok")}
            for k, v in bad.items():
                lines.append(f"- ⚠️ {k} : {v}")
            upd = st.get("updated_at")
            if upd:
                lines.append(f"- Dernier check : {dt.datetime.fromtimestamp(int(upd)).strftime('%F %H:%M')}")
            return "\n".join(lines)
        return f"- état brut : {str(st)[:300]}"
    except Exception as e:
        return f"- (sonde indisponible : {e})"


def timers():
    try:
        out = subprocess.run(
            ["systemctl", "--user", "list-timers", "--no-pager"],
            capture_output=True, text=True, timeout=15).stdout
        keep = [l for l in out.splitlines()
                if any(w in l for w in ("nightly", "survivors", "paper-forward", "health",
                                        "blocktrades", "funding-bulk", "registry", "x-nightly"))]
        return "\n".join(f"- {l.strip()[:150]}" for l in keep[:9]) or "- (aucun timer actif)"
    except Exception as e:
        return f"- (systemctl indisponible : {e})"


def derniers_rapports():
    try:
        cands = sorted(glob.glob(str(ROOT / "reports" / "**" / "*.md"), recursive=True),
                       key=lambda p: Path(p).stat().st_mtime, reverse=True)
        skip = ("the-machine-", "/briefing/")
        rows = []
        for p in cands:
            rel = Path(p).relative_to(ROOT / "reports")
            if any(s in str(rel) for s in skip):
                continue
            mtime = dt.datetime.fromtimestamp(Path(p).stat().st_mtime).strftime("%F %H:%M")
            rows.append(f"- [`{rel}`](../reports/{rel}) — {mtime}")
            if len(rows) >= 6:
                break
        return "\n".join(rows) or "- (aucun rapport)"
    except Exception as e:
        return f"- ({e})"


def main():
    today = dt.date.today().strftime("%F")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    body = f"""# BRIEFING MATINAL — {today}

*Généré par `scripts/daily_briefing.py` (lecture seule). La carte complète des
fronts vit dans Ariad/Obsidian : `Modules/carte-des-fronts-…`.*

## 1. Forward paper — survivants T21 (le verdict 90 j)

{survivors_forward()}

## 2. Machine nocturne (dernier run)

{machine_nocturne()}

## 3. Santé des sondes

{health()}

## 4. Timers 24/7

{timers()}

## 5. Derniers rapports (toutes domaines)

{derniers_rapports()}

## 6. Tirs à venir + décisions ouvertes

{TIRS_A_VENIR}
"""
    out = OUT_DIR / f"briefing-{today}.md"
    out.write_text(body, encoding="utf-8")
    print(f"BRIEFING OK -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
