#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OPÉRATION x501 — QA STATIQUE des collecteurs d'observation v10.

Contrôles (inspirés de qa_scanner_x501.py, 49 contrôles) :
  C1  équilibres : () [] {} par fichier
  C2  //@version=3 en ligne 1
  C3  define(title=..., position=..., axis=...) présent
  C4  aucune instruction strategy.* (collecteur = zéro ordre)
  C5  toutes les séries déclarées au niveau racine (anti-repaint) :
      aucun timeseries/static/func dans un bloc conditionnel
  C6  alert(...) au niveau racine, message= et condition= présents
  C7  idiomes doc : source(type="buy_sell_volume"), tv.cells, sumBids/
      sumAsks(orderbookData, depthPct=), funding_rate(...).value, request(...)
  C8  indexation [1] pour bougie fermée (anti-repaint) sur les features
  C9  na-guard isnum sur les venues (cookbook) pour le CVD 4 venues
  C10 detection nouvelle bougie : static lastLogged + isFresh
  C11 inputs complets ET utilisés
Sortie : console + scripts/x501_v10_results/qa_observe.json
"""
import json
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # racine du repo
KS_DIR = os.path.join(BASE, "scripts", "studies", "x501_openmarket")
OUT = os.path.join(BASE, "scripts", "x501_v10_results")
os.makedirs(OUT, exist_ok=True)
FILES = [
    os.path.join(KS_DIR, "x501_observe_flow_H1.ks"),
    os.path.join(KS_DIR, "x501_observe_cvd4_btc_H1.ks"),
    os.path.join(BASE, "download", "kscript", "x501_observe_om_v29.ks"),
]

def eq_bal(s, op, cl):
    """Équilibre en ignorant chaînes et commentaires."""
    s = re.sub(r"//[^\n]*", "", s)
    s = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
    return s.count(op) == s.count(cl)

results, n_ok = {}, 0
for path in FILES:
    name = os.path.basename(path)
    src = open(path).read()
    lines = src.split("\n")
    checks = {}

    for op, cl in (("(", ")"), ("[", "]"), ("{", "}")):
        checks[f"C1_equilibre_{op}{cl}"] = eq_bal(src, op, cl)
    checks["C2_version_ligne1"] = lines[0].strip().startswith("//@version=3")
    checks["C3_define"] = ("define(title=" in src and "position=" in src
                           and "axis=" in src)
    # C4 : aucune instruction strategy.* HORS commentaires (collecteur = zéro ordre)
    code_only = re.sub(r"//[^\n]*", "", src)
    checks["C4_zero_ordre"] = "strategy." not in code_only

    # C5 : déclarations au niveau racine (colonne 0, pas indentées)
    bad = [i + 1 for i, l in enumerate(lines)
           if re.match(r"^\s+(timeseries|static|func)\s", l)]
    checks["C5_series_racine"] = not bad
    checks["_C5_lignes"] = bad

    # C6 : alerte racine avec message= et condition=
    alerts = [i + 1 for i, l in enumerate(lines)
              if "alert(" in l and not l.strip().startswith("//")]
    checks["C6_alerte_racine"] = (len(alerts) == 1
                                  and all(lines[a - 1].startswith("alert(")
                                          for a in alerts)
                                  and "message=" in src and "condition=" in src)

    checks["C7_idiomes_doc"] = True
    if name.startswith("x501_observe_flow"):
        # v13 : source() normalisé en forme nommée canonique source(type=...,
        # symbol=..., exchange=...) conformément à la doc data-sources.
        for idiome in ["ohlcv(symbol=", "trade_volume_by_size(",
                       'source(type="orderbook", symbol=', "sumBids(", "sumAsks(",
                       "funding_rate(", "request(symbol=", "tv.cells",
                       "filter((c)", "reduce((a, b) => a + b, 0)",
                       "depthPct=", "fr.value[1]"]:
            if idiome not in src:
                checks["C7_idiomes_doc"] = False
    elif name.startswith("x501_observe_cvd4"):
        for idiome in ["ohlcv(symbol=", 'source(type="buy_sell_volume"',
                       ".buy[1]", ".sell[1]", "isnum(b) && isnum(s)"]:
            if idiome not in src:
                checks["C7_idiomes_doc"] = False

    checks["C8_bougie_fermee_[1]"] = ("[1]" in src)

    if name.startswith("x501_observe_cvd4"):
        # le guard est FACTORISÉ dans pairDelta/pairLive (2 occurrences)
        # et les 4 venues passent par ces fonctions (aucun accès brut)
        checks["C9_na_guard"] = (src.count("isnum(b) && isnum(s)") >= 2
                                 and src.count("pairDelta(") == 5
                                 and src.count("pairLive(") == 5)
    else:
        checks["C9_na_guard"] = True  # carnet : bookRatio protégé par ternaire

    checks["C10_nouvelle_bougie"] = ("static lastLogged" in src
                                     and "var isFresh = barIndex != lastLogged"
                                     in src and "lastLogged = barIndex" in src)

    inputs = re.findall(r'input\(name="(\w+)"', src)
    used = all(re.search(rf"\b{v}\b", re.sub(r'input\(name="(\w+)".*', "", src)
                         or src) for v in inputs)
    checks["C11_inputs_utilises"] = used and len(inputs) > 0
    checks["_inputs"] = inputs

    ok = all(v for k, v in checks.items() if not k.startswith("_"))
    n_ok += ok
    results[name] = dict(passed=ok, checks=checks)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  "
          f"({sum(1 for k, v in checks.items() if not k.startswith('_') and v)}"
          f"/{sum(1 for k in checks if not k.startswith('_'))} contrôles)")
    for k, v in checks.items():
        if k.startswith("_") or v:
            continue
        print(f"      ECHEC {k} : {v}")

with open(os.path.join(OUT, "qa_observe.json"), "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\n{n_ok}/{len(FILES)} fichiers PASS -> {OUT}/qa_observe.json")
