#!/usr/bin/env python3
"""audit_check.py — revérifie, sur le checkout COURANT, les constats de l'audit du 2026-10-02.

Audit d'origine : commit 1e17712 (387 commits). Rapport (docs/39) épinglé sur 0eef5c8 (411 commits).
Chaque contrôle dit si le problème est TOUJOURS là ([PROBLÈME]) ou corrigé ([OK]).
Stdlib pure, lecture seule. Code de sortie = nombre de PROBLÈMES (0 = propre) -> branchable en CI.

    python3 scripts/audit_check.py
    python3 scripts/audit_check.py --trades chemin.csv    # autre pool (colonnes R, entree_utc)

Le script fait foi sur l'état courant ; le rapport Markdown n'est qu'un instantané daté.
"""
import argparse
import collections
import csv
import glob
import json
import math
import os
import random
import re
import statistics as st
import subprocess
import sys
from math import comb
from pathlib import Path
from statistics import NormalDist


def sh(*args):
    try:
        return subprocess.run(args, capture_output=True).stdout.decode("utf-8", "replace")
    except OSError:
        return ""


ROOT = Path(sh("git", "rev-parse", "--show-toplevel").strip() or ".")
os.chdir(ROOT)
RES = []  # (statut, id, titre, détail)


def add(ok, cid, title, detail=""):
    RES.append(("OK" if ok else "PROBLÈME", cid, title, detail))


def info(cid, title, detail):
    RES.append(("INFO", cid, title, detail))


def lines(path):
    p = ROOT / path
    return p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []


def grep(path, pat):
    return [(i + 1, l.strip()) for i, l in enumerate(lines(path)) if re.search(pat, l)]


ap = argparse.ArgumentParser()
ap.add_argument("--trades", default="scripts/studies/x501_openmarket/trades_v8_deep.csv")
ap.add_argument("--fail-on", default="", help="ids séparés par des virgules : le code de sortie ne compte QUE ces contrôles (CI bloquante)")
args = ap.parse_args()
tracked = [f for f in sh("git", "ls-files").split("\n") if f]

# ---- A. Config de l'agent ---------------------------------------------------------------
cible_re = r"[Cc]ible(?: user)?\s*:\s*60-70"  # la CIBLE affirmée, pas une mention qui l'explique
cible = grep(".zcode/agents/quant-researcher.md", cible_re) + grep(".zcode/skills/quant-discipline/SKILL.md", cible_re)
add(not cible, "A1", "Cible « 60-70 %/mois stables » encore dans les prompts de l'agent",
    "; ".join(f"l.{n}: {t[:60]}" for n, t in cible))
inj = grep(".zcode/agents/quant-researcher.md", r"injectAgentsMd:\s*true")
lim = [t for _, t in grep("AGENTS.md", r"^- max 2 fichiers|^- max 2 lectures|^- max 5 itérations")]
add(not (inj and lim), "A2", "AGENTS.md (mode correction de bugs : max 2 fichiers / 2 lectures) injecté dans l'agent chercheur",
    f"injectAgentsMd=true: {bool(inj)} ; limites: {lim[:3]}")
use = grep(".zcode/agents/quant-researcher.md", r"lab_ledger\.py")
add(bool(use), "A4", "L'agent chercheur est instruit d'appeler lab_ledger.py (check avant, log après)",
    f"références dans quant-researcher.md: {len(use)}")
mod = grep(".zcode/agents/quant-researcher.md", r"^model:")
info("A3", "Modèle de l'agent chercheur", mod[0][1] if mod else "introuvable")

# ---- B. Reproductibilité ----------------------------------------------------------------
kernel = [f for f in tracked if re.search(r"x501_mc_v1[0-2]\.py$", f)]
sim = sh("git", "grep", "-l", "def simulate_ratchet", "--", "*.py").strip()
add(bool(kernel) and bool(sim), "B1", "Noyau Monte-Carlo (simulate_ratchet v12) versionné dans git",
    f"modules v10-v12 suivis: {len(kernel)}/3 ; simulate_ratchet défini: {bool(sim)}")

bad = []
for f in sh("git", "grep", "-l", "/home/z/", "--", "*.py").split():
    if f.endswith("scripts/audit_check.py"):
        continue  # le motif de recherche lui-même contient la chaîne
    L = lines(f)
    for i, l in enumerate(L):
        if "/home/z/" in l and not any(("environ" in x or "EXT_ROOT" in x) for x in L[max(0, i - 3):i + 1]):
            bad.append(f"{Path(f).name}:{i + 1}")
add(not bad, "B2", "Chemins sandbox /home/z/ en dur (sans surcharge par variable d'environnement)",
    f"{len(bad)} ligne(s): {', '.join(bad[:12])}")

mcs = []
for f in glob.glob("scripts/studies/x501_openmarket/*mc_v*.json"):
    m = re.search(r"mc_v(\d+)", f)
    if m:
        mcs.append((int(m.group(1)), f))
latest = max(mcs) if mcs else None
if latest:
    txt = "\n".join(lines("docs/25-openmarket-x501.md"))
    add(bool(re.search(rf"v{latest[0]}\b", txt)), "B3", f"docs/25 cite le MC le plus récent (v{latest[0]})",
        f"occurrences de v20 dans docs/25: {len(re.findall(r'v20', txt))}")
wf = [f for f in tracked if f.startswith(".github/workflows/")]
add(bool(wf), "B4", "CI GitHub (workflows) présente", f"{len(wf)} workflow(s)")

# ---- C. Mémoire anti-boucle et gouvernance ----------------------------------------------
mort = "\n".join(lines("docs/lab/mortuary.md"))
need = {"LSR": r"\bLSR\b", "flux taker": r"taker", "OI": r"\bOI\b|open.interest"}
miss = [k for k, p in need.items() if not re.search(p, mort, re.I)]
add(not miss, "C1", "Mortuary : familles OpenMarket déjà tuées (vagues OI, LSR, taker) enregistrées",
    f"absentes: {miss} ; lignes du fichier: {len(mort.splitlines())}")
hyp = [f for f in tracked if re.match(r"(docs/lab|research)/hypotheses/", f) and not f.endswith(("README.md", ".gitkeep"))]
add(bool(hyp), "C2", "Hypothèses pré-enregistrées en fichiers machine (hypotheses/)", f"{len(hyp)} fichier(s)")
uses = sh("git", "grep", "-l", "backtest_v2", "--", "scripts/studies/x501_openmarket").split()
add(bool(uses), "C3", "Les études x501 passent par backtest_v2 (multiplicité / DSR / candidats)",
    f"{len(uses)} fichier(s) x501 l'utilisent")
ledp = ROOT / "research/ledger/trials.jsonl"
n_led = len([l for l in lines("research/ledger/trials.jsonl") if l.strip()]) if ledp.exists() else 0
sp = ROOT / "research/STATE.md"
add(n_led > 0 and sp.exists() and sp.stat().st_size <= 3000, "C4",
    "Ledger d'essais cumulatif non vide (research/ledger/trials.jsonl) + research/STATE.md ≤ 3 Ko",
    f"entrées du ledger: {n_led} ; STATE.md: {'absent' if not sp.exists() else str(sp.stat().st_size) + ' o'}")
om = [f for f in tracked if f.startswith("research/") and re.search(r"openmarket|x501", f, re.I)]
add(bool(om), "C5", "Registre machine pour le domaine OpenMarket (pool v8, vagues 5-11)", f"{len(om)} fichier(s) research/*openmarket*")

# ---- E. Application réelle de la gouvernance + fiabilité --------------------------------
refs = [f for f in sh("git", "grep", "-l", "-E", "policy\\.yaml", "--", "*.py", "*.sh", "*.service", "*.timer").split()
        if "/archive_studies/" not in f and "/studies/" not in f]
add(bool(refs), "E1", "agent/policy.yaml lue par du code (« appliquée par l'orchestrateur »)",
    f"fichiers exécutables qui la référencent: {refs or 'aucun'}")
svc = "\n".join(lines("configs/systemd-user/trading-agent-nightly.service"))
scripts = sorted(set(re.findall(r"scripts/([A-Za-z0-9_]+\.py)", svc)))
tot = nobad = 0
e2_bad = []
for s_ in scripts:
    L = lines("scripts/" + s_)
    for i, l in enumerate(L):
        if "sqlite3.connect(" in l:
            tot += 1
            if not any("timeout" in x for x in L[i:i + 3]):
                nobad += 1
                e2_bad.append(f"{s_}:{i + 1}")
add(nobad == 0, "E2", "Scripts du nocturne : sqlite3.connect() sans timeout (cause du crash « database is locked » du 02/10)",
    f"{nobad}/{tot} appels directs sans timeout dans {len(scripts)} scripts : {', '.join(e2_bad[:6]) or 'aucun'}")
info("E3", "protocol_v2 ratifié (tag protocol-v2-ratified)",
     "oui" if sh("git", "tag", "-l", "protocol-v2-ratified").strip() else "non — reste une PROPOSITION (décision utilisateur)")

# ---- F. Le gate du ledger, les scellés, l'adaptateur, STATE.md (vérifie les « fix » annoncés) ------
LL = ROOT / "scripts/lab_ledger.py"
if LL.exists():
    r = subprocess.run([sys.executable, str(LL), "selftest"], capture_output=True)
    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip().splitlines()
    add(r.returncode == 0, "F1", "lab_ledger.py passe son selftest (doublon reformulé, plafonds famille/stratégie/total, NUL/SOUS_PUISSANT, ISO week, backfill)",
        (out[-1] if out else "")[:150] or f"rc={r.returncode}")
    r = subprocess.run([sys.executable, str(LL), "status"], capture_output=True)
    m = re.search(r"(\d+)/(\d+) (?:consomm|expérience)", (r.stdout).decode("utf-8", "replace"))
    if not m:
        m = re.search(r"Budget cette semaine : (\d+)/(\d+)", (r.stdout).decode("utf-8", "replace"))
    if m:
        used, cap = int(m.group(1)), int(m.group(2))
        add(used <= cap, "F2", "Budget hebdomadaire du ledger cohérent (un gate toujours rouge apprend à l'agent à l'ignorer)",
            f"{used}/{cap}")
else:
    add(False, "F1", "scripts/lab_ledger.py présent", "absent")

seal_bad = []
seal_n = 0
for script in [f for f in tracked if f.startswith("scripts/") and f.endswith(".py")]:
    txt = "\n".join(lines(script))
    seals = dict(re.findall(r'^(EXPECTED\w*SEAL)\s*=\s*"([0-9a-f]{64})"', txt, re.M))
    if not seals:
        continue
    for hyp in [f for f in tracked if re.match(r"(docs/lab|research)/hypotheses/.*\.md$", f)]:
        if Path(hyp).name in txt:
            h = __import__("hashlib").sha256((ROOT / hyp).read_bytes()).hexdigest()
            seal_n += 1
            if h not in seals.values():
                seal_bad.append(f"{hyp} (script {Path(script).name})")
add(not seal_bad, "F3", "Pré-enregistrements scellés : le sha256 de chaque fichier cité par un script scellé correspond (sinon le script refuse de tourner)",
    f"{seal_n} fichier(s) vérifié(s) ; rompus: {seal_bad or 'aucun'}")

ADP = ROOT / "scripts/studies/x501_openmarket/x501_multiplicity_adapter.py"
if ADP.exists():
    r = subprocess.run([sys.executable, str(ADP)], capture_output=True, cwd=ROOT)
    tail = (r.stdout + r.stderr).decode("utf-8", "replace").strip().splitlines()
    add(r.returncode == 0, "F4", "L'adaptateur de multiplicité x501 s'exécute (il plantait à l'import)", (tail[-1] if tail else "")[:150])
else:
    add(False, "F4", "Adaptateur de multiplicité x501 présent", "absent")

st_p = ROOT / "research/STATE.md"
if st_p.exists() and LL.exists():
    r = subprocess.run([sys.executable, str(LL), "status", "--md"], capture_output=True)
    gen = r.stdout.decode("utf-8", "replace").strip()
    add(bool(gen) and gen in st_p.read_text(encoding="utf-8"), "F5",
        "research/STATE.md contient le bloc LEDGER à jour (python3 scripts/lab_ledger.py sync-state)",
        "bloc absent ou périmé" if gen not in st_p.read_text(encoding="utf-8") else "à jour")
bz = grep(".zcode/agents/bonsai.md", r"^injectAgentsMd:\s*true")
az = (ROOT / "AGENTS.md").stat().st_size if (ROOT / "AGENTS.md").exists() else 0
info("F6", "Agent local Bonsai : AGENTS.md injecté dans son contexte" if bz else "Agent local Bonsai : AGENTS.md non injecté",
     f"AGENTS.md = {az} octets ≈ {int(az / 3.6)} jetons rajoutés à CHAQUE appel du modèle local" if bz else "contexte minimal")

# ---- D. Statistique (le tableau de bord) ------------------------------------------------
tp = ROOT / args.trades
if tp.exists():
    rows = list(csv.DictReader(open(tp, encoding="utf-8")))
    R = [float(r["R"]) for r in rows]
    mo = [r["entree_utc"][:7] for r in rows]
    day = [r["entree_utc"][:10] for r in rows]
    n, mu, sd = len(R), st.mean(R), st.stdev(R)
    g = collections.defaultdict(list)
    for x, m in zip(R, mo):
        g[m].append(x)
    se_c = math.sqrt(sum(sum(x - mu for x in v) ** 2 for v in g.values())) / n
    random.seed(7)
    keys, bs = list(g), []
    for _ in range(4000):
        bs.append(st.mean([x for k in random.choices(keys, k=len(keys)) for x in g[k]]))
    bs.sort()
    lo, hi = bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs))]
    k5 = max(1, int(n * 0.05))
    rest = sorted(R, reverse=True)[k5:]

    def tt(x):
        return st.mean(x) / (st.stdev(x) / math.sqrt(len(x))) if len(x) > 2 else float("nan")

    add(lo > 0 and n >= 400, "D1", "Edge établi : borne basse IC95 (bootstrap par blocs-mois) > 0 et n ≥ 400",
        f"n={n} E[R]={mu:+.3f} t_iid={mu / (sd / math.sqrt(n)):.2f} t_blocs-mois={mu / se_c:.2f} "
        f"IC95=[{lo:+.3f};{hi:+.3f}] ({len(keys)} mois)")
    add(st.mean(rest) > 0, "D1b", f"E[R] reste > 0 sans les {k5} meilleurs trades (top 5 %)",
        f"E[R] hors top 5 % = {st.mean(rest):+.3f}")
    a = [x for x, d in zip(R, day) if d < "2023-12-28"]
    b = [x for x, d in zip(R, day) if d >= "2023-12-28"]
    info("D1c", "Découpe IS/OOS (frontière 2023-12-28)",
         f"IS n={len(a)} E[R]={st.mean(a):+.3f} t={tt(a):.2f} | OOS n={len(b)} E[R]={st.mean(b):+.3f} t={tt(b):.2f}")
    # puissance du critère « >= 5 fenêtres de 2 mois sur 6 avec E[R] > 0 » (protocol_v2, critère 3)
    nd = NormalDist()
    per_win = max(2, round(n / len(keys) * 2))

    def p_ge(k, m, p):
        return sum(comb(m, j) * p ** j * (1 - p) ** (m - j) for j in range(k, m + 1))

    p80 = next(x / 1000 for x in range(500, 1000) if p_ge(5, 6, x / 1000) >= 0.80)
    edge80 = nd.inv_cdf(p80) * sd / math.sqrt(per_win)
    info("D4", f"protocol_v2 critère 5/6 — ILLUSTRATION sur ce pool ({per_win} trades/fenêtre, sd={sd:.2f} R ; "
               f"les trades Aster ne sont pas dans git)",
         f"P(passer | edge nul) = {p_ge(5, 6, 0.5):.2f} ; edge détectable à 80 % de puissance ≥ {edge80:.2f} R "
         f"(pool observé : {mu:+.3f} R)")
else:
    info("D1", "Pool de trades introuvable", str(tp))

if latest:
    try:
        d = json.load(open(latest[1]))
        w0 = next((v for k, v in d.get("scenarios", {}).items() if k.startswith("W0")), None)
        p12, mdd = w0.get("jalon_50100_p12"), w0.get("maxdd_med")
        add(bool(p12), "D2", f"Objectif ×501 en 12 mois : P > 0 dans le MC v{latest[0]} (W0)", f"P = {p12} %")
        add(mdd is not None and mdd < 24.5, "D3", "maxDD simulé non saturé par le plancher mécanique à 25 %",
            f"médiane des maxDD = {mdd} % (≈ 25 % = plancher du simulateur, pas une mesure)")
    except Exception as e:  # structure JSON inconnue
        info("D2", "MC non lisible", repr(e))

# ---- Sortie -----------------------------------------------------------------------------
print(f"AUDIT CHECK — HEAD {sh('git', 'log', '-1', '--format=%h %ad', '--date=short').strip()} "
      f"(audit d'origine 1e17712 ; rapport sur 0eef5c8)\n")
tags = {"OK": "[OK]      ", "PROBLÈME": "[PROBLÈME]", "INFO": "[info]    "}
for status, cid, title, det in RES:
    print(f"{tags[status]} {cid:<4} {title}" + (f"\n             ↳ {det}" if det else ""))
FAIL_ON = {x.strip() for x in args.fail_on.split(",") if x.strip()}
n_bad = sum(1 for r in RES if r[0] == "PROBLÈME" and (not FAIL_ON or r[1] in FAIL_ON))
n_all = sum(1 for r in RES if r[0] != "INFO")
print(f"\n{sum(1 for r in RES if r[0] == 'PROBLÈME')} problème(s) sur {n_all} contrôles"
      + (f" — bloquants ({len(FAIL_ON)} suivis) : {n_bad}" if FAIL_ON else ""))
sys.exit(min(n_bad, 125))
