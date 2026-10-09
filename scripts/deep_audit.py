#!/usr/bin/env python3
"""deep_audit.py — détecteurs AST des classes de bugs réellement rencontrées.

Trois oracles existent déjà (audit_check.py = constats datés du 2026-10-02,
audit_except_pass.py = rochet `except: pass`, bandit-baseline). Ils ne
couvrent PAS les familles de défauts qui ont coûté le plus de corrections
manuelles — chaque occurrence a été trouvée à la main, et RIEN ne
redétecterait une réintroduction :

  G1  mélange secondes/millisecondes dans une même expression
      (bug P0 ronde 10 : lentille OI lue en ms, fixture en s →
      confluence 3/3 inatteignable en silence) ;
  G2  horodatage fossile RÉCENT figé dans un test sensible au temps
      (issue #235 : timestamps mai 2026 vs fenêtre glissante 30 j →
      3 échecs fantômes dès que le présent a dépassé le figé) ;
  G3  rupture du contrat de données x_pressure (producteur/consommateur :
      nombre de colonnes, ordre, unité de captured_at) ;
  G4  faux succès codé dur — `success=True` coexistant avec une preuve
      d'échec/report dans le MÊME payload (clé errors/failed/deferred/…
      vraie ; les 9 faux succès éliminés à la main proclamaient un succès
      que leurs propres champs réfutaient) ;
  G5  fail-open silencieux dans une fonction verdict/gate/ratchet :
      un handler `except Exception` sans trace et qui rend une valeur
      neutre (le rochet R5 corrigé fail-closed en #252) ;
  G8  horodatage historique figé — info, jamais bloquant : fixture de
      données passées, à requalifier si la logique testée devient
      glissante ;
  G9  fichier .py non parsable (l'oracle pyflakes n'attrape que les noms).

Fenêtre « récent » (G2) : [HEAD − 180 j, HEAD + 1 j] — déterministe par
commit (le HEAD du checkout fait foi), elle suit le repo dans le temps :
un fossile écrit ce mois-ci est chassé, une fixture de 2024 reste une info.

ROCHET (--check, doctrine audit_except_pass : stock mesuré, visible, la
dette cesse de croître) : le compte PAR FICHIER et PAR CLASSE ne doit pas
augmenter ; une réduction est libre et encouragée (--reset dans la PR qui
réduit). Une PR ne peut pas relever sa propre référence : la CI compare
aussi au baseline de origin/main (même second gate que except-pass).

Suppression locale (décision explicite, visible en review) :
    sur la ligne fautive ou juste au-dessus :  # deep-audit:ignore[=G1,G4]
    niveau fichier (partout) :  # deep-audit:ignore-file[=G2]

    python3 scripts/deep_audit.py                 # scan + liste
    python3 scripts/deep_audit.py --check         # gate CI : rochet
    python3 scripts/deep_audit.py --reset         # réécrit la référence
    python3 scripts/deep_audit.py --json out.json # sortie machine

Stdlib pure, lecture seule (sauf --reset), déterministe (tri fixe, aucun
horodatage dans la sortie).
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".github" / "deep-audit-baseline.json"

# Périmètre production : les mêmes racines qu'audit_except_pass.py, hors
# archives. tests/ n'est scanné que pour G2/G8 (fossiles) — un `except: pass`
# y est déjà rochété par audit_except_pass, un payload de test est une
# fixture, pas une mesure.
PROD_RACINES = ("scripts", "backend", "discord_bot", "agent")
EXCL_PARTS = {"archive_studies", "archives", "node_modules", "__pycache__"}

MS_NAME = re.compile(r"(?i)_ms$")          # now_ms, captured_at_ms, ts_ms…

FRESH_RE = re.compile(r"time\.time\(\)|utcnow|datetime\.now\(|date\.today\(")
FOSSIL_WINDOW_DAYS = 180        # un fossile « récent » = < 6 mois du HEAD
EPOCH_HIST_MIN = 1_600_000_000  # plancher G8 (2020-09)

SUCCESS_KEYS = {"success", "ok", "passed", "verified", "healthy"}
# variable de résultat dont l'existence dans la portée rend un succès
# codé dur mensonger (signature #249 : le succès se dérive des results)
RESULT_VAR = re.compile(r"(?i)^(results?|outcomes?|tool_results?|r[0-9]+|r_[a-z0-9_]+)$")
VERDICT_FN = re.compile(r"(?i)verdict|gate|ratchet|enforce|require|must_")
TRACE_ATTRS = {"print", "error", "warning", "info", "exception", "critical",
               "log", "debug", "notice"}

CONTRACT = {
    "producer": "scripts/x_aster_pulse.py",
    "consumer": "scripts/aster_convergence.py",
    "table": "x_pressure",
    "columns": ["ticker", "posts", "posts_prev", "velocity", "longs",
                "shorts", "engagement", "funding_pct", "captured_at"],
    "ts_col": "captured_at",
    "ts_unit": "epoch_seconds",
}

IGNORE_RE = re.compile(r"#\s*deep-audit:ignore(-file)?(?:=([A-Z0-9,]+))?\s*$")

CODES = ("G1", "G2", "G3", "G4", "G5", "G8", "G9")
INFO_CODES = {"G8"}


# ---- outillage ------------------------------------------------------------------------

def head_epoch(root: Path) -> int:
    """Date du HEAD (fenêtre fossile déterministe par commit)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct"],
                             cwd=str(root), capture_output=True, timeout=30)
        return int(out.stdout.decode().strip() or "0")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 0


def iter_prod_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for rac in PROD_RACINES:
        base = root / rac
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            if any(part in EXCL_PARTS for part in p.parts):
                continue
            out.append(p)
    return out


def iter_test_files(root: Path) -> list[Path]:
    tdir = root / "tests"
    return sorted(tdir.rglob("test_*.py")) if tdir.exists() else []


def collect_ign(src: str) -> tuple[dict[int, set[str]], set[str]]:
    """(ligne -> codes ignorés), (codes ignorés au niveau fichier)."""
    ign_lines: dict[int, set[str]] = {}
    ign_file: set[str] = set()
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        m = IGNORE_RE.search(line)
        if not m:
            continue
        codes = {c.strip().upper() for c in (m.group(2) or "").split(",")
                 if c.strip()} or {"ALL"}
        if m.group(1):
            ign_file |= codes
        else:
            ign_lines.setdefault(i, set()).update(codes)
            if i + 1 <= len(lines):  # annotation posée au-dessus du fautif
                ign_lines.setdefault(i + 1, set()).update(codes)
    return ign_lines, ign_file


def _fn_nodes(tree: ast.AST) -> list:
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _is_time_now_call(node: ast.AST) -> bool:
    """time.time() / datetime.now(...).timestamp() — des secondes."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "time" and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "time":
            return True
        if node.func.attr == "timestamp":
            return True
    return False


def _join_literals(txt: str) -> str:
    """Soude les littéraux chaînes adjacents multi-lignes — le SELECT du
    consommateur est écrit sur deux constantes Python voisines."""
    txt = re.sub(r'"\s*\n\s*"', "", txt)
    txt = re.sub(r"'\s*\n\s*'", "", txt)
    return txt


# ---- G1 : mélange secondes / millisecondes --------------------------------------------

def check_g1(add, fn, rel: str) -> None:
    ms_vars: set[str] = set()
    s_vars: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name):
            name, val = n.targets[0].id, n.value
            if _is_time_now_call(val):
                if MS_NAME.search(name):
                    # nom *_ms mais valeur en secondes : contradiction
                    # nom/valeur (le producteur a menti à la variable)
                    add("G1", rel, n, f"variable {name} nommée *_ms mais "
                        "assignée en secondes (.timestamp()/time.time()) — "
                        "l'unité du nom ne correspond pas à la valeur")
                else:
                    s_vars.add(name)
            elif isinstance(val, ast.BinOp) and isinstance(val.op, ast.Mult):
                sides = [val.left, val.right]
                if any(isinstance(s, ast.Constant)
                       and s.value in (1000, 1000.0, 1_000_000)
                       for s in sides):
                    other = next((s for s in sides
                                  if not isinstance(s, ast.Constant)), None)
                    if other is not None and (
                            _is_time_now_call(other)
                            or (isinstance(other, ast.Name)
                                and other.id in (s_vars | ms_vars))):
                        ms_vars.add(name)

    def is_ms(name: str) -> bool:
        return MS_NAME.search(name) is not None or name in ms_vars

    def is_sec(node: ast.AST) -> bool:
        return _is_time_now_call(node) or (
            isinstance(node, ast.Name)
            and (node.id in s_vars or node.id == "now"))

    for n in ast.walk(fn):
        pair = None
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Sub, ast.Add)):
            pair = (n.left, n.right)
        elif isinstance(n, ast.Compare) and len(n.ops) == 1:
            pair = (n.left, n.comparators[0])
        if pair:
            left, right = pair
            l_ms = isinstance(left, ast.Name) and is_ms(left.id)
            r_ms = isinstance(right, ast.Name) and is_ms(right.id)
            l_sec, r_sec = is_sec(left), is_sec(right)
            if (l_ms and r_sec) or (l_sec and r_ms):
                add("G1", rel, n, "mélange secondes/millisecondes dans la "
                    "même expression (bug P0 ronde 10 : lentille OI)")
            # now_ms - float(x_non_ms) : la face non ms n'est pas convertie
            for ms_side, other in ((left, right), (right, left)):
                if isinstance(ms_side, ast.Name) and is_ms(ms_side.id) \
                        and isinstance(other, ast.Call) \
                        and isinstance(other.func, ast.Name) \
                        and other.func.id in ("float", "int") and other.args \
                        and isinstance(other.args[0], ast.Name) \
                        and not is_ms(other.args[0].id):
                    add("G1", rel, n, f"expression en ms mélangée à float("
                        f"{other.args[0].id}) non converti — unité du "
                        "producteur non prouvée (contrat G3)")
            # nom *_ms mais valeur en secondes : contradiction nom/valeur
            for side in (left, right):
                if isinstance(side, ast.Name) and MS_NAME.search(side.id) \
                        and side.id in s_vars:
                    add("G1", rel, n, f"variable {side.id} nommée *_ms mais "
                        "assignée en secondes (.timestamp()/time.time())")


# ---- G2/G8 : fossiles dans les tests sensibles au temps -------------------------------

def check_g2(add, tree: ast.AST, rel: str, head_ts: int) -> None:
    if head_ts <= 0:
        return
    lo_recent = head_ts - FOSSIL_WINDOW_DAYS * 86400
    hi_recent = head_ts + 86400
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, int) \
                and not isinstance(n.value, bool):
            v = n.value
            if lo_recent <= v <= hi_recent:
                add("G2", rel, n, f"horodatage figé {v} (récent : "
                    f"{FOSSIL_WINDOW_DAYS} j autour du HEAD) dans un test "
                    "qui utilise l'heure courante — fossile possible "
                    "(classe #235)")
            elif lo_recent * 1000 <= v <= hi_recent * 1000:
                add("G2", rel, n, f"horodatage ms figé {v} (récent) dans un "
                    "test qui utilise l'heure courante — fossile possible "
                    "(classe #235)")
            elif EPOCH_HIST_MIN <= v < lo_recent:
                add("G8", rel, n, f"horodatage historique figé {v} — info "
                    "(fixture passée, à requalifier si la logique testée "
                    "est glissante)")


# ---- G3 : contrat de données x_pressure -----------------------------------------------

def check_g3(add, root: Path, ptxt: str | None = None,
             ctxt: str | None = None) -> None:
    prod = root / CONTRACT["producer"]
    cons = root / CONTRACT["consumer"]
    table = CONTRACT["table"]
    n_decl = len(CONTRACT["columns"])
    if ptxt is None:
        if not prod.exists():
            add("G3", CONTRACT["producer"], 0,
                f"producteur du contrat {table} absent")
            return
        ptxt = prod.read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table}\s*\((.*?)\)",  # nosec B608 — motif de CONTRAT (regex), aucun SQL exécuté
                  ptxt, re.S)
    if not m:
        add("G3", CONTRACT["producer"], 0, f"DDL de {table} introuvable")
    else:
        cols = [c.strip() for c in m.group(1).split(",")]
        cols = [c for c in cols if c and not re.match(
            r"(?i)PRIMARY\s+KEY|FOREIGN|UNIQUE|CHECK|CONSTRAINT", c)]
        if len(cols) != n_decl:
            add("G3", CONTRACT["producer"], 0,
                f"DDL {table} : {len(cols)} colonnes, contrat en exige "
                f"{n_decl}")
        else:
            got = [c.split()[0] for c in cols]
            if got != CONTRACT["columns"]:
                add("G3", CONTRACT["producer"], 0,
                    f"DDL {table} : {got} ≠ contrat {CONTRACT['columns']}")
    mi = re.search(
        rf"INSERT(?: OR REPLACE)? INTO {table}\s*VALUES\s*\(([?,\s]+)\)",
        ptxt)
    if not mi:
        add("G3", CONTRACT["producer"], 0, f"INSERT INTO {table} introuvable")
    elif mi.group(1).count("?") != n_decl:
        add("G3", CONTRACT["producer"], 0,
            f"INSERT {table} : {mi.group(1).count('?')} placeholders, "
            f"contrat en exige {n_decl}")
    if not re.search(r"datetime\.now\([^)]*\)\.timestamp\(\)", ptxt):
        add("G3", CONTRACT["producer"], 0,
            f"unité de {CONTRACT['ts_col']} non prouvée : aucune écriture "
            "en secondes epoch (.timestamp()) dans le producteur")
    if re.search(r"time\.time\(\)\s*\*\s*1000", ptxt):
        add("G3", CONTRACT["producer"], 0,
            f"producteur écrit du ms alors que le contrat "
            f"{CONTRACT['ts_col']} est en secondes")
    if ctxt is None and cons.exists():
        ctxt = cons.read_text(encoding="utf-8-sig", errors="replace")
    if ctxt is not None:
        ctxt = _join_literals(ctxt)
        mc = re.search(rf"SELECT\s+(.+?)\s+FROM\s+{table}\b", ctxt, re.S)
        if mc:
            sel = [c.strip()
                   for c in mc.group(1).replace("\n", " ").split(",")]
            decl = CONTRACT["columns"]
            hors = [c for c in sel if c and c not in decl]
            if hors:
                add("G3", CONTRACT["consumer"], 0,
                    f"colonnes lues hors contrat : {hors}")
            order = [decl.index(c) for c in sel if c in decl]
            if order != sorted(order):
                add("G3", CONTRACT["consumer"], 0,
                    "ordre des colonnes lues ≠ ordre du contrat "
                    "(déballage positionnel fragile)")
        else:
            add("G3", CONTRACT["consumer"], 0,
                f"SELECT FROM {table} introuvable chez le consommateur")


# ---- G4 : faux succès codé dur --------------------------------------------------------

def check_g4(add, tree: ast.AST, rel: str) -> None:
    """Signature #249 : un dict `success: True` CODÉ DUR dans une fonction
    qui possède une variable de résultat (result/results/…) assignée
    AVANT le dict — le résultat existe mais le succès l'ignore."""
    for fn in _fn_nodes(tree):
        result_lines: list[tuple[int, str]] = []
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name) and RESULT_VAR.match(t.id):
                        result_lines.append((n.lineno, t.id))
        if not result_lines:
            continue
        for n in ast.walk(fn):
            if not isinstance(n, ast.Dict):
                continue
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) \
                        and k.value.lower() in SUCCESS_KEYS \
                        and isinstance(v, ast.Constant) and v.value is True:
                    antérieurs = {name for ln, name in result_lines
                                  if ln < n.lineno}
                    # un payload qui LIT le résultat est informé — seul le
                    # succès qui l'IGNORE est mensonger
                    lus = {x.id for x in ast.walk(n)
                           if isinstance(x, ast.Name)}
                    if antérieurs and not (antérieurs & lus):
                        add("G4", rel, n, f"faux succès codé dur : "
                            f"\"{k.value}\": True alors que "
                            f"{sorted(antérieurs)[0]} (résultat réel) est en "
                            "portée mais ignoré par ce payload — le succès "
                            "se dérive des résultats (signature #249)")
                    break


# ---- G5 : fail-open silencieux dans les fonctions verdict/gate -------------------------

def _handler_silent(h: ast.ExceptHandler) -> bool:
    for s in h.body:
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
            fn = s.value.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (
                fn.id if isinstance(fn, ast.Name) else "")
            if name in TRACE_ATTRS:
                return False
    for s in h.body:
        if isinstance(s, (ast.Pass, ast.Continue)):
            return True
        if isinstance(s, ast.Return) and (
                s.value is None or (isinstance(s.value, ast.Constant)
                                    and not s.value.value)):
            return True
    return False


def check_g5(add, tree: ast.AST, rel: str) -> None:
    for fn in _fn_nodes(tree):
        if not VERDICT_FN.search(fn.name):
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.ExceptHandler) and _handler_silent(n):
                typ = "bare" if n.type is None else (
                    getattr(n.type, "id", None) or ast.dump(n.type))
                add("G5", rel, n, f"{fn.name}(): fail-open silencieux "
                    f"({typ}) — un gate qui avale sans trace rend "
                    "indétectable le cas qu'il doit bloquer")


# ---- scan + suppressions ---------------------------------------------------------------

def scan(root: Path = ROOT, head_ts: int | None = None) -> list[dict]:
    if head_ts is None:
        head_ts = head_epoch(root)
    items: list[dict] = []
    seen: set[tuple] = set()

    def add(code: str, rel: str, node, msg: str) -> None:
        line = getattr(node, "lineno", 0) or 0
        key = (code, rel, line, msg)
        if key in seen:
            return
        seen.add(key)
        items.append({"code": code, "file": rel, "line": line, "msg": msg})

    ign_map: dict[str, tuple[dict[int, set[str]], set[str]]] = {}

    for p in iter_prod_files(root):
        rel = str(p.relative_to(root))
        src = p.read_text(encoding="utf-8-sig", errors="replace")
        ign_map[rel] = collect_ign(src)
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError) as e:
            add("G9", rel, getattr(e, "lineno", 0),
                f"non parsable : {getattr(e, 'msg', e)}")
            continue
        for fn in _fn_nodes(tree):
            check_g1(add, fn, rel)
        check_g4(add, tree, rel)
        check_g5(add, tree, rel)
    for p in iter_test_files(root):
        rel = str(p.relative_to(root))
        src = p.read_text(encoding="utf-8-sig", errors="replace")
        ign_map[rel] = collect_ign(src)
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            continue
        if FRESH_RE.search(src):
            check_g2(add, tree, rel, head_ts)
    check_g3(add, root)

    # suppressions (décision explicite visible en review)
    kept: list[dict] = []
    for it in items:
        ign_lines, ign_file = ign_map.get(it["file"], ({}, set()))
        if "ALL" in ign_file or it["code"] in ign_file:
            continue
        codes = ign_lines.get(it["line"], set())
        if "ALL" in codes or it["code"] in codes:
            continue
        kept.append(it)
    return sorted(kept,
                  key=lambda d: (d["code"], d["file"], d["line"], d["msg"]))


# ---- rochet ----------------------------------------------------------------------------

def per_file_counts(items: list[dict]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for it in items:
        out.setdefault(it["file"], {}).setdefault(it["code"], 0)
        out[it["file"]][it["code"]] += 1
    return out


def ratchet_verdict(items: list[dict], base: dict) -> tuple[int, list[str]]:
    """(nb de régressions, lignes de détail). Régression = un fichier dont
    le compte d'une classe AUGMENTE, ou un total qui augmente. Une
    réduction est libre (notice)."""
    cur = per_file_counts(items)
    details: list[str] = []
    n_reg = 0
    tot_c = sum(sum(v.values()) for v in cur.values())
    tot_b = sum(sum(v.values()) for v in base.values())
    for f, codes in sorted(cur.items()):
        b_f = base.get(f, {})
        for c, n in sorted(codes.items()):
            if n > b_f.get(c, 0):
                n_reg += 1
                details.append(f"{f} : {c} {b_f.get(c, 0)} -> {n}")
    if tot_c > tot_b:
        details.append(f"total {tot_b} -> {tot_c}")
        n_reg += 1
    return n_reg, details


def load_baseline(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return {k: {c: int(n) for c, n in v.items()} for k, v in d.items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError,
            AttributeError):
        return {}


# ---- CLI -------------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fail-on", default="",
                    help="codes bloquants (G1,G2,…) ; vide = tous hors info")
    ap.add_argument("--check", action="store_true",
                    help="gate CI : rochet dette courante <= baseline")
    ap.add_argument("--baseline", default=None,
                    help="baseline ALTERNATIVE (la CI compare à origin/main)")
    ap.add_argument("--reset", action="store_true",
                    help="réécrit la référence (PR de réduction uniquement)")
    ap.add_argument("--json", dest="json_path", default=None,
                    help="écrit les constats en JSON (diffable)")
    a = ap.parse_args(argv)

    items = scan()
    if a.json_path:
        Path(a.json_path).write_text(
            json.dumps(items, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")

    if a.reset:
        cur = per_file_counts(items)
        BASELINE.write_text(
            json.dumps(cur, indent=1, sort_keys=True, ensure_ascii=False)
            + "\n", encoding="utf-8")
        tot = sum(sum(v.values()) for v in cur.values())
        print(f"référence réécrite : {tot} constat(s) sur {len(cur)} "
              f"fichier(s) -> {BASELINE.relative_to(ROOT)}")
        print("Ne l'utiliser QUE dans une PR qui RÉDUIT la dette : relever "
              "la référence sans rien corriger, c'est effacer l'alarme.")
        return 0

    for it in items:
        print(f"[{it['code']}] {it['file']}:{it['line']} — {it['msg']}")

    if a.check:
        path = Path(a.baseline) if a.baseline else BASELINE
        base = load_baseline(path)
        if not base:
            print(f"::error::baseline deep-audit absente/illisible "
                  f"({path}) — `python3 scripts/deep_audit.py --reset` "
                  "(et commite la référence)")
            return 1
        n_reg, details = ratchet_verdict(items, base)
        if n_reg:
            for d in details:
                print(f"::error::deep-audit régression : {d}")
            print("le rochet interdit l'augmentation — corrige, ou réduis "
                  "et commit la nouvelle référence dans la PR")
            return 1
        tot_c = sum(sum(v.values()) for v in per_file_counts(items).values())
        tot_b = sum(sum(v.values()) for v in base.values())
        if tot_c < tot_b:
            print(f"::notice::dette deep-audit réduite de {tot_b - tot_c} "
                  f"({tot_b} -> {tot_c}) — pense à --reset dans la PR")
        else:
            print(f"deep-audit stable à {tot_c} constat(s)")
        return 0

    fail_on = {x.strip().upper() for x in a.fail_on.split(",") if x.strip()}
    n_bad = sum(1 for it in items
                if it["code"] not in INFO_CODES
                and (not fail_on or it["code"] in fail_on))
    n_codes = sorted({it["code"] for it in items})
    print(f"\ndeep_audit : {len(items)} constat(s) {n_codes}"
          + (f" — bloquants ({','.join(sorted(fail_on))}) : {n_bad}"
             if fail_on else f" — bloquants (tous hors info) : {n_bad}"))
    return min(n_bad, 125)


if __name__ == "__main__":
    sys.exit(main())
