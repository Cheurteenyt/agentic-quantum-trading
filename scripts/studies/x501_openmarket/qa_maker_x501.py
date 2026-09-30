#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QA statique des kScripts MAKER x501 (versions *_MK.ks, v20).

Contrôles spécifiques à l'instrumentation maker δ=2–5, en complément de la QA
générale (qa_kscript_x501.py) qui reste applicable au squelette commun :
  M1  en-tête version + strategy() première instruction
  M2  inputs maker complets avec contraintes
  M3  persists maker déclarés exactement une fois
  M4  verrou de file : les 2 signaux exigent pendSide == 0
  M5  entrées : branches maker avec limit=, branches taker inchangées
  M6  strategy.cancel des 2 ids (L/S) dans l'expiration/invalidation
  M7  invalidation : clôture au-delà du stop prévu (2 côtés), sans fallback
  M8  fallback : conditionné, pendFb=1, et boucle d'expiration fermée au fallback
  M9  transfert pend->plan complet au fill (side/qty/stop/entry/fillDone)
  M10 alert() = uniquement le rapport fin de run sur isLastBar (vague 3)
  M11 flash de fill reseté en fin de script
  M12 équilibre accolades/parenthèses du code
  M13 non-régression : chaque ligne de l'original est une sous-séquence du MK
      (exceptions doctrinales : les 3 lignes remplacées P5A/B/C, le commentaire
      bracket remplacé vague 3, et les lignes "upgradées" vague 3 — celles que
      le MK PROLONGE avec ocaName/trail natif : même tête de ligne, + kwargs)
  M14 identifiants non déclarés : aucun (réutilise la whitelist de la QA générale)
  M15 marqueurs chart fill maker/fallback présents
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_kscript_x501 import (strip_comments_strings, qadir, BUILTINS, GLOBALS,  # noqa
                             KWARGS, LANG)

DL = Path(__file__).resolve().parent
PAIRS = [
    (DL / "Operation_x501_Signature_H4.ks", DL / "Operation_x501_Signature_H4_MK.ks"),
    (DL / "Operation_x501_Signature_H1.ks", DL / "Operation_x501_Signature_H1_MK.ks"),
]

PERSIST_MK = ["pendSide", "pendQty", "pendStop", "pendAge", "pendFb",
              "fillMode", "fillFlash", "mkFills", "mkFb", "mkTOut", "mkInv"]


def is_subsequence(small, big):
    it = iter(big)
    return all(any(line == b for b in it) for line in small)


def check_pair(orig: Path, mk: Path):
    src_o = orig.read_text(encoding="utf-8")
    src = mk.read_text(encoding="utf-8")
    lines = src.splitlines()
    code = strip_comments_strings(src)
    msgs = []
    print(f"\n=== {mk.name} ===")

    # M1
    qadir(msgs, "M1 //@version=3 + strategy() en tête",
          lines[0].strip() == "//@version=3" and
          bool(re.search(r"(?m)^\s*strategy\s*\(", code)))

    # M2 inputs maker
    for name in ["makerMode", "makerDeltaBps", "makerTTL", "fallbackTaker"]:
        qadir(msgs, f"M2 input {name} déclaré",
              bool(re.search(rf'input\(name="{name}"', src)))
    qadir(msgs, "M2 contraintes delta (0.5–20) et TTL (1–12)",
          'min: 0.5, max: 20' in src and 'min: 1, max: 12' in src)
    qadir(msgs, "M2 groupe « Exécution maker »", 'group="Exécution maker"' in src)

    # M3 persists
    pers = re.findall(r"(?m)^\s*persist\s+(\w+)", code)
    missing = [p for p in PERSIST_MK if p not in pers]
    dupes = [p for p in pers if pers.count(p) > 1]
    qadir(msgs, f"M3 persists maker x{len(PERSIST_MK)} (manquants {missing}, doublons {dupes})",
          not missing and not dupes)

    # M4 verrous de file
    qadir(msgs, "M4 verrou pendSide == 0 sur longSignal",
          "flat && pendSide == 0 && regimeLong" in code)
    qadir(msgs, "M4 verrou pendSide == 0 sur shortSignal",
          "flat && pendSide == 0 && regimeShort" in code)

    # M5 entrées (recherche dans src : les chaînes y sont intactes)
    qadir(msgs, "M5 limite long : limit=limL présent",
          bool(re.search(r'strategy\.entry\("L",\s*"long",\s*qty=qtyL,\s*limit=limL', src)))
    qadir(msgs, "M5 limite short : limit=limS présent",
          bool(re.search(r'strategy\.entry\("S",\s*"short",\s*qty=qtyS,\s*limit=limS', src)))
    qadir(msgs, "M5 branches taker inchangées (2 entries marché, ocaName vague 3 en fin)",
          'strategy.entry("L", "long", qty=qtyL, comment="x501 long", ocaName="x501L")' in src and
          'strategy.entry("S", "short", qty=qtyS, comment="x501 short", ocaName="x501S")' in src)
    qadir(msgs, "M5 delta bps : long sous le prix, short au-dessus",
          "trade.close * (1 - makerDeltaBps / 10000)" in code and
          "trade.close * (1 + makerDeltaBps / 10000)" in code)

    # M6 cancel
    qadir(msgs, "M6 strategy.cancel L et S", src.count('strategy.cancel(pendSide == 1 ? "L" : "S")') == 2)

    # M7 invalidation
    qadir(msgs, "M7 invalidation stop 2 côtés (sans fallback)",
          "(pendSide == 1 && trade.close <= pendStop)" in code and
          "(pendSide == -1 && trade.close >= pendStop)" in code and
          "mkInv = mkInv + 1" in code)

    # M8 fallback
    qadir(msgs, "M8 fallback conditionné + pendFb = 1",
          "if (fallbackTaker == true)" in code and "pendFb = 1;" in code)
    qadir(msgs, "M8 expiration fermée au fallback (boucle pendFb == 0)",
          "pendFb == 0)" in code)
    qadir(msgs, "M8 abandon TTL sans fallback compté (mkTOut)", "mkTOut = mkTOut + 1" in code)

    # M9 transfert
    transfert = ("side = pendSide;" in code and "planQty = pendQty;" in code and
                 "planStop = pendStop;" in code and
                 "planEntry = strategy.positionAvgPrice();" in code and
                 "fillDone = 1;" in code)
    qadir(msgs, "M9 transfert pend->plan au fill complet", transfert)
    qadir(msgs, "M9 compteurs fills maker/fallback", "mkFills = mkFills + 1" in code and
          "mkFb = mkFb + 1" in code)

    # M10 alert() : uniquement le rapport fin de run sur isLastBar (vague 3,
    # docs/27-28) — AUCUNE alerte de signal dans les stratégies _MK
    qadir(msgs, "M10 alert() uniquement le rapport fin de run (isLastBar, 1 appel)",
          code.count("alert(") == 1 and "alert(" in code.split("if (isLastBar)")[-1])

    # M11 flash reset
    qadir(msgs, "M11 fillFlash = 0 en fin de script", "fillFlash = 0;" in code)

    # M12 équilibre
    qadir(msgs, "M12 accolades équilibrées", code.count("{") == code.count("}"))
    qadir(msgs, "M12 parenthèses équilibrées", code.count("(") == code.count(")"))

    # M13 non-régression (exceptions : les 3 lignes signal REMPLACÉES par
    # P5A/B/C + le commentaire bracket remplacé par la vague 3)
    replaced = {
        "var longSignal = flat && regimeLong && zoneTouchLong && confluenceOk &&",
        "var shortSignal = flat && regimeShort && zoneTouchShort && confluenceOk &&",
        "cvdUp && bullBar && fundingOkLong && breakersOk;",
        "// Bracket : TP1 (moitié) + TP2 (quart) + runner — le stop est commun",
    }
    orig_lines = [l.strip() for l in src_o.splitlines() if l.strip()
                  and l.strip() not in replaced]
    mk_lines = [l.strip() for l in src.splitlines() if l.strip()]

    def ligne_upgradee_vague3(base_line, mk_set):
        """Une ligne d'origine est "upgradée" (et non perdue) si une ligne du
        MK la PROLONGE : même tête exacte, plus longue (les kwargs vague 3
        ocaName=/trailPoints= sont ajoutés en fin d'appel, jamais insérés au
        milieu — les entries taker, elles, sont vérifiées mot pour mot en M5)."""
        core = base_line
        if core.endswith(");"):
            core = core[:-2]
        elif core.endswith(";"):
            core = core[:-1]
        return any(m.startswith(core) and len(m) > len(core) for m in mk_set)

    mk_set = set(mk_lines)
    orig_effectives = [l for l in orig_lines if not ligne_upgradee_vague3(l, mk_set)]
    qadir(msgs, "M13 original = sous-séquence du MK (aucune ligne perdue, indent. ignorée)",
          is_subsequence(orig_effectives, mk_lines))

    # M14 identifiants inconnus (réutilise la logique QA générale, simplifiée)
    assigned = set(pers)
    assigned |= {m.group(1) for m in re.finditer(r"(?m)^\s*(?:var|static|timeseries)\s+(\w+)\s*=", code)}
    assigned |= {m.group(1) for m in re.finditer(r"(?m)^\s{2}(\w+)\s*=[^=]", code)}
    for m in re.finditer(r"=\s*\[\s*(\w+(?:\s*,\s*\w+)*)\s*\]", code):
        assigned |= {t.strip() for t in m.group(1).split(",")}
    for m in re.finditer(r"(?m)^\s*\[\s*([\w\s,]+?)\s*\]\s*=", code):
        assigned |= {t.strip() for t in m.group(1).split(",")}
    plain = set(re.findall(r"(?<![\w.])([a-z][A-Za-z0-9_]*)\b(?!\s*\()", code))
    members = set(re.findall(r"\.(\w+)", code))
    known = BUILTINS | KWARGS | LANG
    suspects = {i for i in plain
                if i not in assigned and i not in known and i not in GLOBALS
                and i not in members
                and i not in {"USD", "math", "step", "onchart", "offchart", "perps",
                              "spot", "data", "fixed", "pessimistic", "pathHeuristic",
                              "number", "int", "float", "boolean", "string", "text",
                              "slider", "select", "color", "long", "short"}}
    qadir(msgs, f"M14 identifiants non déclarés : {sorted(suspects) if suspects else 'aucun'}",
          not suspects)

    # M15 marqueurs
    qadir(msgs, "M15 marqueurs fill maker/fallback",
          'label=["Fill maker"]' in src and 'label=["Fill taker-fb"]' in src)

    fails = 0
    for status, label in msgs:
        mark = "  PASS " if status == "OK" else ">>FAIL "
        if status != "OK":
            fails += 1
        print(f"{mark}{label}")
    return fails


if __name__ == "__main__":
    total = 0
    for o, m in PAIRS:
        if not m.exists():
            print(f">>FAIL fichier manquant : {m}")
            total += 1
            continue
        total += check_pair(o, m)
    print(f"\n{'=' * 50}\nQA MAKER : {'PASS — 0 échec' if total == 0 else f'{total} échec(s)'}")
    sys.exit(1 if total else 0)
