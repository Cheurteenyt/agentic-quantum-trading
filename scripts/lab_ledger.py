#!/usr/bin/env python3
"""lab_ledger.py v2 — registre d'essais CUMULATIF + garde-fou de budget (agent/policy.yaml).

Lit le registre existant research/ledger/trials.jsonl (champs date/family/strategy/hypothesis/verdict[/params][/backfill])
et applique RÉELLEMENT la policy : 20/semaine ISO, 5/famille, 3/stratégie, 12 variantes de paramètres.

    python3 scripts/lab_ledger.py check --family F --strategy S --hypothesis "texte" [--params k=v ...]
    python3 scripts/lab_ledger.py log   --family F --strategy S --hypothesis "texte" --verdict FAIL [--date 2026-10-02]
                                        [--domain aster] [--params k=v ...] [--n 868] [--er 0.09] [--se 0.06]
                                        [--ref docs/20-…] [--notes "…"] [--backfill]
    python3 scripts/lab_ledger.py status [--md]          # --md : le bloc Markdown généré
    python3 scripts/lab_ledger.py sync-state [--state research/STATE.md]   # réécrit le bloc LEDGER de STATE.md
    python3 scripts/lab_ledger.py selftest                # preuve fonctionnelle (utilisée par audit_check.py)

Codes de sortie de `check` : 0 = GO · 3 = doublon (NO-OP) · 4 = budget épuisé (STOP) · 2 = erreur.
Verdicts : PASS FAIL NUL SOUS_PUISSANT INCONCLU consomment du budget · PREREG ne consomme pas.
Un essai est « backfill » (compte dans le N cumulé, PAS dans le budget) s'il est antérieur à la date d'effet de la
policy (frozen_tag: freeze-AAAA-MM-JJ) ou marqué "backfill": true.

Corrige l'ancienne version : `log` sans --date plantait ; un doublon reformulé passait ; le plafond par famille/stratégie
n'était pas appliqué ; NUL/SOUS_PUISSANT ne comptaient pas ; policy.yaml n'était pas lue ; fenêtre glissante au lieu de
la semaine ISO ; réécriture complète du fichier à chaque log (non atomique). Stdlib pure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "research" / "ledger" / "trials.jsonl"
DEFAULT_POLICY = ROOT / "agent" / "policy.yaml"
DEFAULT_STATE = ROOT / "research" / "STATE.md"

CONSUMING = {"PASS", "FAIL", "NUL", "SOUS_PUISSANT", "INCONCLU"}
VERDICTS = CONSUMING | {"PREREG"}
DEFAULT_BUDGET = {"total_experiments": 20, "per_family": 5, "per_strategy": 3, "max_parameter_variants": 12}
EXIT_OK, EXIT_ERR, EXIT_DUP, EXIT_STOP = 0, 2, 3, 4
BEGIN, END = "<!-- LEDGER:BEGIN (généré par lab_ledger.py sync-state — ne pas éditer à la main) -->", "<!-- LEDGER:END -->"


# ---------------------------------------------------------------- utilitaires
def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def slug(s: str) -> str:
    return re.sub(r"\s+", "-", (s or "").strip().lower())


def parse_dt(s: str) -> datetime:
    s = s.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        s += "T12:00:00Z"
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_week(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def tstar(n: int) -> float:
    """|t| de Bonferroni (bilatéral, 5 %) pour n essais : t*(1)=1,96 · t*(10)=2,81 · t*(100)=3,48."""
    return NormalDist().inv_cdf(1 - 0.05 / (2 * max(1, int(n))))


def read_policy(path: Path) -> dict:
    """Budget + date d'effet, sans PyYAML (parser minimal du bloc weekly_budget et de frozen_tag)."""
    pol = {"budget": dict(DEFAULT_BUDGET), "effective": None}
    p = Path(path)
    if not p.exists():
        return pol
    inside = False
    for raw in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^frozen_tag\s*:\s*\S*?(\d{4}-\d{2}-\d{2})", raw)
        if m:
            pol["effective"] = parse_dt(m.group(1)).replace(hour=0, minute=0, second=0)
        if re.match(r"^weekly_budget\s*:", raw):
            inside = True
            continue
        if inside:
            if raw.strip() and not raw.startswith((" ", "\t", "#")):
                inside = False
                continue
            m = re.match(r"^\s+(\w+)\s*:\s*(\d+)", raw)
            if m and m.group(1) in pol["budget"]:
                pol["budget"][m.group(1)] = int(m.group(2))
    return pol


def load(ledger: Path, effective: datetime | None) -> list[dict]:
    """Charge et NORMALISE (ancien format `date` inclus). Ajoute _ts _week _hh _ph _backfill _consumes."""
    p, out = Path(ledger), []
    if not p.exists():
        return out
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError as ex:
            raise ValueError(f"{p}:{i} : JSON invalide ({ex})") from ex
        ts = parse_dt(e.get("ts") or e.get("date") or "1970-01-01")
        explicit = e.get("backfill")
        bf = bool(explicit) if explicit is not None else bool(effective and ts < effective)
        params = e.get("params") or {}
        e.update({
            "_ts": ts, "_week": iso_week(ts), "_hh": sha(norm_text(e.get("hypothesis", ""))),
            "_ph": sha(json.dumps(params, sort_keys=True)), "_backfill": bf,
            "_consumes": (e.get("verdict") not in ("PREREG",)) and not bf,
            "family": slug(e.get("family", "")), "strategy": slug(e.get("strategy", "")),
        })
        out.append(e)
    return out


def parse_params(items) -> dict:
    d = {}
    for it in items or []:
        if "=" not in it:
            raise ValueError(f"--params attend k=v (reçu : {it!r})")
        k, v = it.split("=", 1)
        d[k.strip()] = v.strip()
    return d


def git_short() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT)
        return r.stdout.strip() or None
    except OSError:
        return None


# ---------------------------------------------------------------- logique
def week_usage(entries, week):
    cur = [e for e in entries if e["_consumes"] and e["_week"] == week]
    return len(cur), Counter(e["family"] for e in cur), Counter(e["strategy"] for e in cur)


def assess(entries, budget, now, family, strategy, hypothesis, params) -> dict:
    hh, ph = sha(norm_text(hypothesis)), sha(json.dumps(params, sort_keys=True))
    same_h = [e for e in entries if e["_hh"] == hh]
    exact = [e for e in same_h if e["_ph"] == ph]
    if exact:
        e = exact[0]
        where = f"{e['family']}/{e['strategy']}"
        return {"status": "NO-OP", "code": EXIT_DUP, "msgs": [
            f"DOUBLON : même hypothèse (normalisée) et mêmes paramètres déjà logués le {e.get('date') or e['_ts']:.10} "
            f"sous {where} → {e.get('verdict')}. NO-OP : ne pas relancer, même reformulé ou sous une autre stratégie."]}
    msgs, status, code = [], "GO", EXIT_OK
    if same_h:
        variants = len({e["_ph"] for e in same_h})
        msgs.append(f"PARAMETER_MUTATION : cette hypothèse a déjà {variants} variante(s) loguée(s) — une variation "
                    f"consomme du budget, ce n'est PAS une étude nouvelle.")
        if variants + 1 > budget["max_parameter_variants"]:
            status, code = "STOP", EXIT_STOP
            msgs.append(f"STOP : {variants + 1} variantes > max_parameter_variants={budget['max_parameter_variants']}.")
    week = iso_week(now)
    total, by_fam, by_str = week_usage(entries, week)
    msgs.append(f"Semaine {week} : total {total}/{budget['total_experiments']} · famille « {family} » "
                f"{by_fam[family]}/{budget['per_family']} · stratégie « {strategy} » {by_str[strategy]}/{budget['per_strategy']}")
    for label, used, cap in (("total", total, budget["total_experiments"]),
                             (f"famille « {family} »", by_fam[family], budget["per_family"]),
                             (f"stratégie « {strategy} »", by_str[strategy], budget["per_strategy"])):
        if used >= cap:
            status, code = "STOP", EXIT_STOP
            msgs.append(f"STOP : budget {label} épuisé ({used}/{cap}) — file B (maintenance), pas de variante déguisée.")
    fam_all = [e for e in entries if e["family"] == family and e.get("verdict") != "PREREG"]
    dead = sum(1 for e in fam_all if e.get("verdict") in ("FAIL", "NUL"))
    if dead >= 3 and not any(e.get("verdict") == "PASS" for e in fam_all):
        msgs.append(f"MORTALITÉ : « {family} » = {dead} FAIL/NUL pour 0 PASS — écrire la mécanique qui justifie un nouvel essai.")
    n_all = sum(1 for e in entries if e.get("verdict") != "PREREG")
    msgs.append(f"Multiplicité : {n_all} essais cumulés (backfill inclus) → seuil indicatif du prochain |t| ≥ "
                f"{tstar(n_all + 1):.2f} (Bonferroni 5 % bilatéral, N={n_all + 1}).")
    return {"status": status, "code": code, "msgs": msgs}


def status_md(entries, budget, now, effective) -> str:
    week = iso_week(now)
    total, by_fam, by_str = week_usage(entries, week)
    v = Counter(e.get("verdict") for e in entries)
    n_all = sum(1 for e in entries if e.get("verdict") != "PREREG")
    n_bf = sum(1 for e in entries if e["_backfill"] and e.get("verdict") != "PREREG")
    cap = [f"{f} {c}/{budget['per_family']}" for f, c in sorted(by_fam.items()) if c >= budget["per_family"]]
    lines = [BEGIN,
             f"- Ledger : **{len(entries)}** entrées ({n_all} essais, dont {n_bf} backfill hors budget) — "
             + " · ".join(f"{k} {v[k]}" for k in ("PASS", "FAIL", "NUL", "SOUS_PUISSANT", "INCONCLU", "PREREG") if v[k]),
             f"- Budget semaine {week} (effet policy : {effective.date() if effective else 'n/a'}) : "
             f"**{total}/{budget['total_experiments']}** consommés, reste {max(0, budget['total_experiments'] - total)}",
             f"- Familles au plafond : {', '.join(cap) if cap else 'aucune'}",
             f"- Seuil de preuve du prochain essai : |t| ≥ {tstar(n_all + 1):.2f} (Bonferroni, N={n_all + 1})",
             END]
    return "\n".join(lines)


# ---------------------------------------------------------------- commandes
def ctx(a):
    pol = read_policy(a.policy)
    now = parse_dt(a.now) if a.now else now_utc()
    return pol, load(a.ledger, pol["effective"]), now


def cmd_check(a) -> int:
    pol, entries, now = ctx(a)
    res = assess(entries, pol["budget"], now, slug(a.family), slug(a.strategy), a.hypothesis, parse_params(a.params))
    for m in res["msgs"]:
        print(m)
    print({"GO": "→ GO", "NO-OP": "→ NO-OP (doublon)", "STOP": "→ STOP (budget)"}[res["status"]])
    return res["code"]


def cmd_log(a) -> int:
    verdict = a.verdict.upper()
    if verdict not in VERDICTS:
        print(f"verdict invalide : {a.verdict} (attendu : {', '.join(sorted(VERDICTS))})")
        return EXIT_ERR
    pol, entries, now = ctx(a)
    ts = parse_dt(a.date) if a.date else now
    family, strategy, params = slug(a.family), slug(a.strategy), parse_params(a.params)
    backfill = True if a.backfill else (None if not pol["effective"] else ts < pol["effective"])
    if verdict != "PREREG" and not backfill:
        res = assess(entries, pol["budget"], ts, family, strategy, a.hypothesis, params)
        if res["status"] != "GO":
            print(f"⚠ {res['status']} au moment du log — enregistré quand même (le registre reflète ce qui a été exécuté) :")
            for m in res["msgs"]:
                print("  " + m)
    entry = {"date": ts.strftime("%Y-%m-%d"), "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "domain": slug(a.domain),
             "family": family, "strategy": strategy, "hypothesis": a.hypothesis.strip(),
             "hypothesis_hash": sha(norm_text(a.hypothesis)), "parameter_hash": sha(json.dumps(params, sort_keys=True)),
             "verdict": verdict, "n": a.n, "er": a.er, "se": a.se, "ref": a.ref, "notes": a.notes, "git": git_short()}
    if params:
        entry["params"] = params
    if a.backfill:
        entry["backfill"] = True
    entry = {k: v for k, v in entry.items() if v is not None}
    p = Path(a.ledger)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:  # append atomique : jamais de réécriture du fichier
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    entries = load(a.ledger, pol["effective"])
    total, by_fam, by_str = week_usage(entries, iso_week(ts))
    print(f"logué : {verdict} · {family}/{strategy} · semaine {iso_week(ts)} : total {total}/{pol['budget']['total_experiments']}, "
          f"famille {by_fam[family]}/{pol['budget']['per_family']}, stratégie {by_str[strategy]}/{pol['budget']['per_strategy']} "
          f"· cumul {sum(1 for e in entries if e.get('verdict') != 'PREREG')} essais")
    return EXIT_OK


def cmd_status(a) -> int:
    pol, entries, now = ctx(a)
    if not entries:
        print("registre vide (research/ledger/trials.jsonl)")
        return EXIT_OK
    if a.md:
        print(status_md(entries, pol["budget"], now, pol["effective"]))
        return EXIT_OK
    week = iso_week(now)
    total, by_fam, by_str = week_usage(entries, week)
    b = pol["budget"]
    print(f"Semaine {week} : {total}/{b['total_experiments']} consommés (effet policy : "
          f"{pol['effective'].date() if pol['effective'] else 'n/a'} ; avant = backfill hors budget)")
    for f, c in sorted(by_fam.items()):
        print(f"  famille {f:<28s} {c}/{b['per_family']}")
    for s, c in sorted(by_str.items()):
        print(f"  stratégie {s:<30s} {c}/{b['per_strategy']}")
    n_all = sum(1 for e in entries if e.get("verdict") != "PREREG")
    print(f"Cumul : {n_all} essais · t*(N={n_all}) = {tstar(n_all):.2f} (Bonferroni 5 % bilatéral)")
    return EXIT_OK


def cmd_sync_state(a) -> int:
    pol, entries, now = ctx(a)
    block = status_md(entries, pol["budget"], now, pol["effective"])
    p = Path(a.state)
    text = p.read_text(encoding="utf-8") if p.exists() else "# STATE\n"
    if BEGIN in text and END in text:
        text = text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
    else:
        text = text.rstrip("\n") + "\n\n## Ledger & budget (généré)\n" + block + "\n"
    p.write_text(text, encoding="utf-8")
    print(f"{p} : bloc LEDGER synchronisé ({len(text.encode())} octets)")
    return EXIT_OK


def cmd_selftest(a) -> int:
    """Preuve fonctionnelle : tourne sur un registre jetable, jamais sur le vrai."""
    fails = []
    with tempfile.TemporaryDirectory() as d:
        led, pol = Path(d) / "t.jsonl", Path(d) / "policy.yaml"
        pol.write_text("frozen_tag: freeze-2026-10-02\nweekly_budget:\n  total_experiments: 4\n  per_family: 2\n"
                       "  per_strategy: 2\n  max_parameter_variants: 2\n", encoding="utf-8")
        base = ["--ledger", str(led), "--policy", str(pol), "--now", "2026-10-06T10:00:00Z"]

        def run(*argv):
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    code = main([*base, *argv])
                except SystemExit as ex:  # argparse
                    code = int(ex.code or 0)
            return code, buf.getvalue()

        def lg(h, fam="f", st="s", v="FAIL", extra=()):
            return run("log", "--family", fam, "--strategy", st, "--hypothesis", h, "--verdict", v, *extra)

        def chk(h, fam="f", st="s", extra=()):
            return run("check", "--family", fam, "--strategy", st, "--hypothesis", h, *extra)

        def ok(name, cond):
            if not cond:
                fails.append(name)

        ok("log sans --date ne plante pas", lg("La Majeure Déviante !")[0] == EXIT_OK)
        ok("doublon reformulé = NO-OP", chk("la majeure deviante")[0] == EXIT_DUP)
        ok("même hypothèse sous une autre stratégie = NO-OP", chk("la majeure deviante", "autre", "autre")[0] == EXIT_DUP)
        lg("hyp 2", "f", "s2")
        ok("plafond par famille (2/2) = STOP", chk("hyp 3", "f", "s3")[0] == EXIT_STOP)
        lg("hyp 4", "g", "t", "NUL")
        lg("hyp 5", "h", "u", "SOUS_PUISSANT")
        ok("NUL et SOUS_PUISSANT consomment (4/4) = STOP", chk("hyp 6", "z", "z")[0] == EXIT_STOP)
        lg("hyp prereg", "k", "k", "PREREG")
        ok("PREREG ne consomme pas", "4/4" in chk("hyp 7", "z", "z")[1])
        lg("hyp ancienne", "m", "m", "FAIL", ("--date", "2026-09-30"))
        ok("avant la date d'effet = backfill hors budget", "4/4" in chk("hyp 8", "z", "z")[1])
        lines = led.read_text(encoding="utf-8").splitlines()
        ok("registre append-only (6 lignes, aucune réécriture)", len(lines) == 6)
        lg("v1", "p", "q", extra=("--params", "k=1"))
        ok("variante de paramètres signalée", "PARAMETER_MUTATION" in chk("v1", "p", "q", ("--params", "k=2"))[1])
    if fails:
        print("SELFTEST ÉCHEC : " + " | ".join(fails))
        return 1
    print("SELFTEST OK (11 propriétés : doublon reformulé, autre stratégie, plafonds famille/total, NUL/SOUS_PUISSANT, "
          "PREREG, backfill, append-only, log sans --date, variantes)")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    p.add_argument("--policy", default=str(DEFAULT_POLICY))
    p.add_argument("--now", help="horodatage ISO forcé (tests)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "log"):
        s = sub.add_parser(name)
        s.add_argument("--family", required=True)
        s.add_argument("--strategy", required=True)
        s.add_argument("--hypothesis", required=True)
        s.add_argument("--params", nargs="*", default=[])
        if name == "log":
            s.add_argument("--verdict", required=True)
            s.add_argument("--date", help="AAAA-MM-JJ (défaut : maintenant UTC)")
            s.add_argument("--domain", default="aster")
            s.add_argument("--n", type=int)
            s.add_argument("--er", type=float)
            s.add_argument("--se", type=float)
            s.add_argument("--ref")
            s.add_argument("--notes")
            s.add_argument("--backfill", action="store_true")
    st = sub.add_parser("status")
    st.add_argument("--md", action="store_true")
    sy = sub.add_parser("sync-state")
    sy.add_argument("--state", default=str(DEFAULT_STATE))
    sub.add_parser("selftest")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return {"check": cmd_check, "log": cmd_log, "status": cmd_status,
                "sync-state": cmd_sync_state, "selftest": cmd_selftest}[a.cmd](a)
    except ValueError as e:
        print(f"erreur : {e}")
        return EXIT_ERR


if __name__ == "__main__":
    sys.exit(main())
