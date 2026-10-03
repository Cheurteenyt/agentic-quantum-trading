#!/usr/bin/env python3
"""bonsai_verify.py — ancre chaque affirmation du modèle local dans le code/les docs, ou la rejette.

Pourquoi : un modèle 2-bit sur 8 Go hallucine dès que le contexte grossit (audit de the_machine.py : 6 « réels » sur 16 selon
l'en-tête du rapport, 5 sur 15 selon le commit, 4 lignes réelles dans le tableau). On ne lui demande JAMAIS un jugement ni un
chiffre : on lui demande des affirmations CITÉES (fichier + extrait verbatim) que ce script vérifie mécaniquement. Le juge
final (GLM ou toi) ne voit que les affirmations ANCRÉES, et la précision est CALCULÉE, pas recomptée à la main.

    python3 scripts/bonsai_verify.py chunks scripts/the_machine.py --lines 100 --overlap 10 [--out /tmp/chunks]
    python3 scripts/bonsai_verify.py verify claims.json --task code-audit [--model bonsai-27b] [--no-log]
    python3 scripts/bonsai_verify.py judge <uid> real|false
    python3 scripts/bonsai_verify.py score [--task code-audit]

claims.json : [{"id": "c1", "claim": "…", "file": "scripts/x.py", "line": 123, "quote": "extrait verbatim"}]
Statuts : GROUNDED (extrait trouvé, proche de la ligne annoncée) · MISPLACED (trouvé, mais loin de la ligne annoncée) ·
          UNGROUNDED (extrait introuvable = halluciné) · BAD_REF (fichier absent ou hors du repo) · VAGUE (extrait < 12 car.)
Journal append-only : research/ledger/bonsai_claims.jsonl. Stdlib pure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "research" / "ledger" / "bonsai_claims.jsonl"
MIN_QUOTE = 12
LINE_TOL = 8
BAD = {"UNGROUNDED", "BAD_REF", "VAGUE"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def safe_path(root: Path, rel: str) -> Path | None:
    if not rel:
        return None
    p = (root / rel).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError:
        return None
    return p if p.is_file() else None


def find_lines(text: str, quote: str) -> list[int]:
    """Numéros de ligne (1-based) où l'extrait apparaît, espaces normalisés, même s'il s'étend sur plusieurs lignes."""
    nq, lines = norm(quote), text.splitlines()
    k = max(1, quote.count("\n") + 1) + 1
    return [i + 1 for i in range(len(lines)) if nq in norm(" ".join(lines[i:i + k]))]


def check_claim(root: Path, c: dict) -> dict:
    quote = c.get("quote") or ""
    res = {"status": None, "found_line": None}
    if len(norm(quote)) < MIN_QUOTE:
        res["status"] = "VAGUE"
        return res
    p = safe_path(root, c.get("file") or "")
    if p is None:
        res["status"] = "BAD_REF"
        return res
    hits = find_lines(p.read_text(encoding="utf-8", errors="replace"), quote)
    if not hits:
        res["status"] = "UNGROUNDED"
        return res
    claimed = c.get("line")
    if isinstance(claimed, int):
        res["found_line"] = min(hits, key=lambda h: abs(h - claimed))
        res["status"] = "GROUNDED" if abs(res["found_line"] - claimed) <= LINE_TOL else "MISPLACED"
    else:
        res["found_line"], res["status"] = hits[0], "GROUNDED"
    return res


def read_log(path: Path) -> list[dict]:
    p = Path(path)
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def append_log(path: Path, entries: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")


def cmd_chunks(a) -> int:
    p = Path(a.file)
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    n, stride = len(lines), max(1, a.lines - a.overlap)
    starts = list(range(0, max(1, n), stride))
    starts = [s for i, s in enumerate(starts) if i == 0 or starts[i - 1] + a.lines < n]
    out = Path(a.out) if a.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(starts, 1):
        e = min(n, s + a.lines)
        body = "\n".join(f"{j + 1:5d}| {lines[j]}" for j in range(s, e))
        head = f"### chunk {i}/{len(starts)} — {p.as_posix()}:L{s + 1}-L{e} (≈ {int(len(body) / 3.6)} jetons)"
        if out:
            (out / f"chunk_{i:02d}.txt").write_text(head + "\n" + body + "\n", encoding="utf-8")
            print(head)
        else:
            print(head + "\n" + body + "\n")
    return 0


def cmd_verify(a) -> int:
    try:
        claims = json.loads(Path(a.claims).read_text(encoding="utf-8"))
        assert isinstance(claims, list) and all(isinstance(c, dict) for c in claims)
    except (OSError, ValueError, AssertionError) as ex:
        print(f"erreur : claims.json doit être une liste d'objets JSON ({ex})")
        return 2
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries, counts = [], Counter()
    for i, c in enumerate(claims, 1):
        r = check_claim(Path(a.root), c)
        counts[r["status"]] += 1
        uid = f"{a.task}:{run}:{c.get('id', i)}"
        entries.append({"type": "claim", "ts": ts, "uid": uid, "task": a.task, "model": a.model, "status": r["status"],
                        "file": c.get("file"), "line": c.get("line"), "found_line": r["found_line"],
                        "claim": (c.get("claim") or "")[:200], "judge": None})
        print(f"{r['status']:<11} {uid}  {c.get('file')}:{c.get('line')}  {(c.get('claim') or '')[:70]}")
    total = len(claims)
    print(f"\nancrées : {counts['GROUNDED']}/{total}" + (f" ({counts['GROUNDED'] / total:.0%})" if total else "")
          + f" · mal placées : {counts['MISPLACED']} · introuvables : {counts['UNGROUNDED']} · "
            f"fichier invalide : {counts['BAD_REF']} · vagues : {counts['VAGUE']}")
    print("→ seul GROUNDED va au juge ; tout le reste est écarté AUTOMATIQUEMENT (halluciné ou invérifiable).")
    if not a.no_log and entries:
        append_log(a.log, entries)
    return 0


def cmd_judge(a) -> int:
    if a.verdict not in ("real", "false"):
        print("verdict : real | false")
        return 2
    known = {e["uid"]: e for e in read_log(a.log) if e.get("type") == "claim"}
    if a.uid not in known:
        print(f"uid inconnu : {a.uid}")
        return 2
    if known[a.uid]["status"] != "GROUNDED":
        print(f"{a.uid} est {known[a.uid]['status']} : écartée d'office, rien à juger")
        return 2
    append_log(a.log, [{"type": "judge", "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "uid": a.uid, "task": known[a.uid]["task"], "judge": a.verdict}])
    print(f"{a.uid} → {a.verdict}")
    return 0


def cmd_score(a) -> int:
    log = read_log(a.log)
    claims = {e["uid"]: e for e in log if e.get("type") == "claim" and (not a.task or e["task"] == a.task)}
    judge = {}
    for e in log:
        if e.get("type") == "judge" and e["uid"] in claims:
            judge[e["uid"]] = e["judge"]
    n = len(claims)
    if not n:
        print("aucune affirmation dans le journal")
        return 0
    st = Counter(e["status"] for e in claims.values())
    grounded = [u for u, e in claims.items() if e["status"] == "GROUNDED"]
    real = sum(1 for u in grounded if judge.get(u) == "real")
    false = sum(1 for u in grounded if judge.get(u) == "false")
    unjudged = len(grounded) - real - false
    print(f"{'tâche ' + a.task if a.task else 'toutes tâches'} : {n} affirmations · " + " · ".join(f"{k} {v}" for k, v in sorted(st.items())))
    print(f"ancrées : {len(grounded)}/{n} ({len(grounded) / n:.0%}) · jugées réelles {real}, fausses {false}, non jugées {unjudged}")
    print(f"précision de bout en bout : borne basse {real / n:.0%} (non jugées = fausses) · borne haute {(real + unjudged) / n:.0%}")
    if n < 30:
        print(f"⚠ n = {n} < 30 : trop peu pour décider si ce type de tâche est fiable (règle : ≥ 30 affirmations jugées).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--log", default=str(DEFAULT_LOG))
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("chunks")
    c.add_argument("file")
    c.add_argument("--lines", type=int, default=100)
    c.add_argument("--overlap", type=int, default=10)
    c.add_argument("--out")
    v = sub.add_parser("verify")
    v.add_argument("claims")
    v.add_argument("--task", default="misc")
    v.add_argument("--model", default="bonsai")
    v.add_argument("--root", default=str(ROOT))
    v.add_argument("--no-log", action="store_true")
    j = sub.add_parser("judge")
    j.add_argument("uid")
    j.add_argument("verdict")
    s = sub.add_parser("score")
    s.add_argument("--task")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    return {"chunks": cmd_chunks, "verify": cmd_verify, "judge": cmd_judge, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
