#!/bin/bash
# premerge_audit.sh — le re-audit avant merge, scripté (doctrine docs/41).
#
# Leçon des merges croisés #243/#237 (ronde 10) : une PR verte sur une
# VIEILLE base ne prouve RIEN — après N merges sur main, sa CI décrit un
# état qui n'existera jamais. D'où des gates, dans cet ordre, chacun
# refusant d'avancer :
#
#   1. fetch + capture de origin/main (MAIN_BEFORE)
#   2. PR ouverte, mergeable, CI verte sur son head
#   3. update-branch (rebase/merge de main DANS la branche) + CI verte sur
#      le NOUVEAU head = la CI a tourné sur l'état fusionné réel
#   4. re-fetch : origin/main n'a PAS bougé pendant qu'on travaillait
#      (sinon : tout recommencer, les suites ciblées ne valent plus rien)
#   5. merge SQUASH épinglé sur le sha vérifié (protection anti-dérive)
#   6. post-merge : main == sha attendu
#
# Usage :
#   GH=<token> bash scripts/premerge_audit.sh <PR_NUMBER> [--merge]
#   --merge   absent : gates 1-4 seulement (dry-run du re-audit)
#
# Token par variable d'environnement GH, JAMAIS en dur, jamais echo.
set -uo pipefail

PR="${1:?usage: GH=... premerge_audit.sh <PR_NUMBER> [--merge]}"
DO_MERGE="no"
[ "${2:-}" = "--merge" ] && DO_MERGE="yes"
REPO="Cheurteenyt/agentic-quantum-trading"
API="https://api.github.com"

: "${GH:?GH manquant — exporte le token en variable d'environnement}"

hdr=(-H "Authorization: Bearer ${GH}" -H "Accept: application/vnd.github+json"
     -H "User-Agent: premerge-audit")

gh_api() { # gh_api METHOD PATH [JSON]
    local m="$1" p="$2" d="${3:-}"
    if [ -n "$d" ]; then
        curl -sS -X "$m" "${hdr[@]}" "$API/repos/$REPO/$p" -d "$d"
    else
        curl -sS -X "$m" "${hdr[@]}" "$API/repos/$REPO/$p"
    fi
}

gate() { # gate NOM rc
    if [ "$2" -eq 0 ]; then
        echo "  [PASS] $1"
    else
        echo "  [FAIL] $1 — ABORT"
        exit 1
    fi
}

echo "== premerge_audit PR #$PR =="

# Gate 1 — fetch + capture de main
git fetch origin --quiet 2>/dev/null
MAIN_BEFORE="$(git rev-parse origin/main)"
gate "fetch + main capturé (${MAIN_BEFORE:0:7})" $?

# Gate 2 — PR ouverte + CI verte sur le head
PRJSON="$(gh_api GET "pulls/$PR")"
STATE="$(echo "$PRJSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('state','?'))")"
HEAD_SHA="$(echo "$PRJSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['head']['sha'])")"
gate "PR #$PR state=$STATE head=${HEAD_SHA:0:7}" \
     $([ "$STATE" = "open" ] && echo 0 || echo 1)

CI_CONCL="$(gh_api GET "commits/$HEAD_SHA/check-runs?per_page=100" | python3 -c "
import json,sys
d=json.load(sys.stdin)
runs=d.get('check_runs',[])
concl={r['conclusion'] for r in runs if r['status']=='completed'}
print('success' if runs and concl=={'success'} else ('pending' if any(r['status']!='completed' for r in runs) else 'failure'))")"
gate "CI du head = success (constaté : $CI_CONCL)" \
     $([ "$CI_CONCL" = "success" ] && echo 0 || echo 1)

# Gate 3 — update-branch puis CI verte sur l'état fusionné réel
UPD="$(gh_api PUT "pulls/$PR/update-branch" '{"expected_head_sha":"'"$HEAD_SHA"'"}')"
UPD_SHA="$(echo "$UPD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sha',''))" 2>/dev/null)"
if [ -n "$UPD_SHA" ] && [ "$UPD_SHA" != "null" ]; then
    echo "  [info] update-branch -> nouveau head ${UPD_SHA:0:7} ; attente CI (poll 60 s)…"
    for _ in $(seq 1 40); do
        sleep 60
        CI_CONCL="$(gh_api GET "commits/$UPD_SHA/check-runs?per_page=100" | python3 -c "
import json,sys
d=json.load(sys.stdin)
runs=d.get('check_runs',[])
if not runs: print('pending'); raise SystemExit
pend=any(r['status']!='completed' for r in runs)
concl={r['conclusion'] for r in runs if r['status']=='completed'}
print('pending' if pend else ('success' if concl=={'success'} else 'failure'))")"
        [ "$CI_CONCL" = "pending" ] || break
    done
    gate "CI sur l'état fusionné = success ($CI_CONCL)" \
         $([ "$CI_CONCL" = "success" ] && echo 0 || echo 1)
    HEAD_SHA="$UPD_SHA"
else
    echo "  [info] update-branch : branche déjà à jour de main"
fi

# Gate 4 — main n'a pas bougé
git fetch origin --quiet 2>/dev/null
MAIN_NOW="$(git rev-parse origin/main)"
gate "origin/main inchangé (${MAIN_BEFORE:0:7})" \
     $([ "$MAIN_NOW" = "$MAIN_BEFORE" ] && echo 0 || echo 1)

if [ "$DO_MERGE" != "yes" ]; then
    echo "== re-audit complet : PR #$PR prête au merge (relance avec --merge) =="
    exit 0
fi

# Gate 5 — merge squash épinglé sur le sha vérifié (ce repo refuse merge_method=merge : 405)
MR="$(gh_api PUT "pulls/$PR/merge" '{"merge_method":"squash","sha":"'"$HEAD_SHA"'"}')"
MERGED="$(echo "$MR" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('merged',''))" 2>/dev/null)"
SHA_EXPECTED="$(echo "$MR" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sha',''))" 2>/dev/null)"
gate "merge squash (merged=$MERGED, sha=${SHA_EXPECTED:0:7})" \
     $([ "$MERGED" = "True" ] && echo 0 || echo 1)

# Gate 6 — post-merge : main == sha attendu
sleep 3
git fetch origin --quiet 2>/dev/null
MAIN_AFTER="$(git rev-parse origin/main)"
gate "post-merge origin/main == ${SHA_EXPECTED:0:7}" \
     $([ "$MAIN_AFTER" = "$SHA_EXPECTED" ] && echo 0 || echo 1)

echo "== PR #$PR mergée proprement : main @ ${MAIN_AFTER:0:7} =="
