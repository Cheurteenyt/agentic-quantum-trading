#!/usr/bin/env python3
"""premerge_audit.sh — le re-audit avant merge, scripté (doctrine docs/41).

Leçon des merges croisés #243/#237 (ronde 10) : une PR verte sur une
VIEILLE base ne prouve RIEN — après N merges sur main, sa CI décrit un
état qui n'existera jamais. D'où des gates, dans cet ordre, chacun
refusant d'avancer :

  1. fetch + capture de origin/main (MAIN_BEFORE)
  2. PR ouverte + CI verte sur son head
  3. update-branch (main fusionné DANS la branche) + CI verte sur le
     NOUVEAU head = la CI a tourné sur l'état fusionné réel
  4. re-fetch : origin/main n'a PAS bougé pendant le re-audit
     (sinon ABORT : les suites ciblées ne valent plus rien, on recommence)
  5. merge SQUASH épinglé sur le sha vérifié (anti-dérive ; ce repo
     refuse merge_method=merge : 405, squash uniquement)
  6. post-merge : origin/main == sha du merge

Usage :
    GH=<token> bash scripts/premerge_audit.sh <PR_NUMBER> [--merge]
    --merge absent : gates 1-4 seulement (dry-run du re-audit)

Token par variable d'environnement GH, JAMAIS en dur, jamais echo.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = "Cheurteenyt/agentic-quantum-trading"
API = "https://api.github.com"
GH = os.environ.get("GH", "")
HDR = {"Authorization": f"Bearer {GH}",
       "Accept": "application/vnd.github+json",
       "User-Agent": "premerge-audit"}


def api(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{API}/repos/{REPO}/{path}", data=data,
                                 headers=HDR, method=method)
    with urllib.request.urlopen(req) as r:  # nosec B310 — URL constantes https de l'API GitHub (doctrine bandit du repo)
        return json.loads(r.read() or b"{}")


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True)
    if out.returncode != 0:
        return ""
    return out.stdout.decode().strip()


def gate(name: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL — ABORT"
    print(f"  [{tag}] {name}" + (f" ({detail})" if detail else ""))
    if not ok:
        sys.exit(1)


def ci_verdict(sha: str) -> str:
    """success | pending | failure — sur tous les check-runs du sha."""
    try:
        d = api("GET", f"commits/{sha}/check-runs?per_page=100")
    except urllib.error.HTTPError as e:
        return f"http_{e.code}"
    runs = d.get("check_runs", [])
    if not runs or any(r["status"] != "completed" for r in runs):
        return "pending"
    return "success" if {r["conclusion"] for r in runs} == {"success"} \
        else "failure"


def wait_ci(sha: str, minutes: int = 40) -> str:
    verdict = "pending"
    for _ in range(minutes):
        verdict = ci_verdict(sha)
        if verdict != "pending":
            return verdict
        time.sleep(60)
    return verdict


def main() -> int:
    if not GH:
        print("GH manquant — exporte le token en variable d'environnement")
        return 2
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__.split("\n")[0])
        print("usage: GH=... premerge_audit.sh <PR_NUMBER> [--merge]")
        return 2
    pr_n = args[0]
    do_merge = "--merge" in sys.argv

    print(f"== premerge_audit PR #{pr_n} ==")

    # Gate 1 — fetch + capture de main
    git("fetch", "origin", "--quiet")
    main_before = git("rev-parse", "origin/main")
    gate("fetch + main capturé", bool(main_before), main_before[:7])

    # Gate 2 — PR ouverte + CI verte sur le head
    pr = api("GET", f"pulls/{pr_n}")
    head = pr["head"]["sha"]
    gate("PR ouverte", pr.get("state") == "open",
         f"state={pr.get('state')} head={head[:7]}")
    v = ci_verdict(head)
    gate("CI du head = success", v == "success", f"constaté : {v}")
    if v == "pending":
        v = wait_ci(head)
        gate("CI du head (après attente) = success", v == "success", v)

    # Gate 3 — update-branch puis CI verte sur l'état fusionné réel
    try:
        upd = api("PUT", f"pulls/{pr_n}/update-branch",
                  {"expected_head_sha": head})
        new_sha = upd.get("sha") or ""
    except urllib.error.HTTPError as e:
        new_sha = ""
        print(f"  [info] update-branch : HTTP {e.code} (déjà à jour)")
    if new_sha and new_sha != head:
        print(f"  [info] update-branch -> nouveau head {new_sha[:7]} ; "
              "attente CI (poll 60 s)…")
        v = wait_ci(new_sha)
        gate("CI sur l'état fusionné = success", v == "success", v)
        head = new_sha
    else:
        print("  [info] update-branch : branche déjà à jour de main")

    # Gate 4 — main n'a pas bougé pendant le re-audit
    git("fetch", "origin", "--quiet")
    main_now = git("rev-parse", "origin/main")
    gate("origin/main inchangé", main_now == main_before, main_before[:7])

    if not do_merge:
        print(f"== re-audit complet : PR #{pr_n} prête au merge "
              "(relance avec --merge) ==")
        return 0

    # Gate 5 — merge squash épinglé sur le sha vérifié
    try:
        mr = api("PUT", f"pulls/{pr_n}/merge",
                 {"merge_method": "squash", "sha": head})
    except urllib.error.HTTPError as e:
        print(f"  [FAIL — ABORT] merge squash : HTTP {e.code} "
              f"{e.read().decode('utf-8', 'replace')[:200]}")
        return 1
    gate("merge squash accepté", mr.get("merged") is True,
         f"sha={str(mr.get('sha', ''))[:7]}")
    sha_expected = mr.get("sha", "")

    # Gate 6 — post-merge : main == sha du merge
    time.sleep(3)
    git("fetch", "origin", "--quiet")
    main_after = git("rev-parse", "origin/main")
    gate("post-merge origin/main == sha du merge",
         main_after == sha_expected, main_after[:7])

    print(f"== PR #{pr_n} mergée proprement : main @ {main_after[:7]} ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
