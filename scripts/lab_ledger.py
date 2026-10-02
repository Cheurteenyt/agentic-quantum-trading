#!/usr/bin/env python3
"""lab_ledger.py — le registre d'essais cumulatif et le garde-fou du budget.

Le gate ANTI-BOUCLLE exécutable : check avant, log après. FAIL compris.

    python3 scripts/lab_ledger.py check --family cascade --strategy machine_cascade_majors --hypothesis "dOI prédit la qualité du short suivant"
    python3 scripts/lab_ledger.py log --family cascade --strategy machine_cascade_majors --hypothesis "..." --verdict FAIL --date 2026-10-02
    python3 scripts/lab_ledger.py status

Codes de sortie : 0 = go · 3 = doublon exact (NO-OP) · 4 = budget épuisé (STOP).
"""
import argparse, json, hashlib, sys, datetime, pathlib

LEDGER = pathlib.Path(__file__).resolve().parents[1] / "research" / "ledger" / "trials.jsonl"
POLICY = pathlib.Path(__file__).resolve().parents[1] / "agent" / "policy.yaml"
WEEKLY_BUDGET = 20

def _hash(s): return hashlib.sha256(s.encode()).hexdigest()[:16]

def _load():
    if not LEDGER.exists(): return []
    return [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]

def _budget_used(entries, week_start):
    return sum(1 for e in entries if e.get("date", "") >= week_start and e.get("verdict") in ("PASS", "FAIL") and not e.get("backfill"))

def cmd_check(a):
    entries = _load()
    h = _hash(f"{a.family}:{a.strategy}:{a.hypothesis}")
    exact = [e for e in entries if e.get("hypothesis_hash") == h]
    if exact:
        print(f"DOUBLON EXACT (hash {h}) — NO-OP. Voir : {exact[0].get('date')} {exact[0].get('verdict')}")
        sys.exit(3)
    from datetime import datetime, timedelta
    week_start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    used = _budget_used(entries, week_start)
    if used >= WEEKLY_BUDGET:
        print(f"BUDGET ÉPUISÉ : {used}/{WEEKLY_BUDGET} cette semaine. STOP — passe à la file B.")
        sys.exit(4)
    fam_count = sum(1 for e in entries if e.get("family") == a.family and e.get("date", "") >= week_start)
    print(f"GO : hash {h} | budget {used}/{WEEKLY_BUDGET} | famille '{a.family}' {fam_count}/5 cette semaine")

def cmd_log(a):
    entries = _load()
    h = _hash(f"{a.family}:{a.strategy}:{a.hypothesis}")
    entry = {"date": a.date or datetime.now().strftime("%Y-%m-%d"),
             "family": a.family, "strategy": a.strategy,
             "hypothesis": a.hypothesis, "hypothesis_hash": h,
             "verdict": a.verdict,
             **({"params": dict(kv.split("=", 1) for kv in a.params)} if a.params else {})}
    entries.append(entry)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n")
    print(f"loggé : {a.verdict} | hash {h} | total cumulé : {len(entries)} essais")

def cmd_status(a):
    entries = _load()
    from collections import Counter
    fams = Counter(e.get("family") for e in entries)
    verdicts = Counter(e.get("verdict") for e in entries)
    print(f"Ledger : {len(entries)} essais cumulés")
    print(f"Verdicts : {dict(verdicts)}")
    print(f"Familles : {dict(fams.most_common(10))}")
    print(f"Budget cette semaine : {_budget_used(entries, (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y-%m-%d'))}/{WEEKLY_BUDGET}")

p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd")
c = sub.add_parser("check"); c.add_argument("--family", required=True); c.add_argument("--strategy", required=True); c.add_argument("--hypothesis", required=True); c.add_argument("--params", nargs="*", default=[])
l = sub.add_parser("log"); l.add_argument("--family", required=True); l.add_argument("--strategy", required=True); l.add_argument("--hypothesis", required=True); l.add_argument("--verdict", required=True); l.add_argument("--date", default=None); l.add_argument("--params", nargs="*", default=[])
s = sub.add_parser("status")
a = p.parse_args()
{"check": cmd_check, "log": cmd_log, "status": cmd_status}.get(a.cmd, lambda x: p.print_help())(a)
