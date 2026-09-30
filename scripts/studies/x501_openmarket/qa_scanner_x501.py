#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QA anti-bug du scanner x501_setup_kscript.js — validation statique
contre la doc kScript v3 scrapée (78 pages, research_ks/pages/)."""
import re
import sys
from pathlib import Path

FICHIER = Path(__file__).resolve().parent / "x501_setup_kscript.js"

# Whitelist issue des pages officielles scrapées
BUILTINS = {
    "sma", "ema", "alma", "swma", "wma", "vwma", "hma", "rma", "rsi", "wpr",
    "cmo", "tsi", "macd", "stoch", "cci", "mfi", "change", "roc", "mom", "adx",
    "psar", "supertrend", "tr", "atr", "hl2", "hlc3", "ohlc4", "hlcc4", "bb",
    "keltner", "stdev", "stddev", "variance", "obv", "vwap", "cum",
    "correlation", "median", "percentile", "linreg", "highest", "lowest",
    "highestbars", "lowestbars", "pivothigh", "pivotlow", "valuewhen",
    "barssince", "rising", "falling", "crossover", "crossunder", "cross",
    "fixnan", "isna", "isnum", "nz", "donchian", "ichimoku",
    "strategy", "input", "plotLine", "plotShape", "plotTable", "plotChar",
    "fillBetween", "alert", "alertcondition", "format", "tostring", "print",
    "strategy.entry", "strategy.exit", "strategy.close", "strategy.closeAll",
    "strategy.cancel", "strategy.cancelAll", "strategy.positionSize",
    "strategy.positionAvgPrice", "strategy.equity", "strategy.openProfit",
    "strategy.netProfit", "strategy.closedTradeCount", "strategy.winTradeCount",
    "strategy.lossTradeCount", "strategy.maxDrawdown",
    "ohlcv", "buy_sell_volume", "source", "htf", "request", "requestBars",
    "math.abs", "math.max", "math.min", "math.sqrt", "math.pow",
    "time", "timenow", "hour", "session", "sessionName",
}
GLOBALS = {"currentSymbol", "currentExchange", "currentCoin", "barIndex",
           "isLastBar", "isConfirmed", "isFirst", "na", "true", "false"}
KWARGS = {"title", "position", "axis", "customTitle", "format", "maxBarsBack",
          "initialCapital", "currency", "commissionPercent", "slippageBps",
          "slippageModel", "qtyType", "qtyValue", "pyramiding", "fillModel",
          "instrument", "leverage", "maintenanceMarginPercent",
          "makerFeePercent", "takerFeePercent", "funding", "onLiquidation",
          "name", "type", "defaultValue", "label", "constraints", "group",
          "options", "symbol", "exchange", "coin", "asset", "delta",
          "timeframe", "opts", "mode", "offset", "bars", "period", "mult",
          "factor", "atrPeriod", "source", "id", "direction", "qty", "limit",
          "stop", "ocaName", "comment", "fromEntry", "profit", "loss",
          "trailPoints", "trailOffset", "value", "colors", "colorIndex",
          "width", "desc", "fill", "smooth", "showPriceDisplay", "shape",
          "glow", "data", "message", "condition", "location", "tooltip",
          "headerRow", "headerColumn", "x", "y", "priceIndex", "anchor", "n",
          "constant", "start", "increment", "maxValue", "depthPct"}
LANG = {"var", "persist", "timeseries", "if", "else", "func", "return", "for",
        "while", "switch", "import", "as", "static", "break", "continue",
        "define"}
SRC_TYPES = {"ohlcv", "open_interest", "buy_sell_volume",
             "trade_volume_by_size", "funding_rate", "liquidations",
             "orderbook", "cme_oi", "deribit_implied_volatility",
             "deribit_volatility_index", "skew", "etf_premium_rate",
             "etf_holding", "options_volume", "options_open_interest",
             "etf_flow", "ethena_positions", "long_short_ratio",
             "binance_treasury_balance", "volume_profile"}
TF_RE = re.compile(r"^\d+(m|h|d)$|^1[DWMQY]$")


def strip_comments_strings(src):
    out, i, n = [], 0, len(src)
    in_str = None
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            out.append(" " if in_str else c)
            i += 1
            continue
        if c in "\"'":
            in_str = c
            out.append(c)
            i += 1
            continue
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def main():
    src = FICHIER.read_text(encoding="utf-8")
    lignes = src.splitlines()
    code = strip_comments_strings(src)
    msgs = []

    def q(label, cond):
        msgs.append((bool(cond), label))

    q("1re ligne = //@version=3", lignes and lignes[0].strip() == "//@version=3")
    m = re.search(r"(?m)^\s*strategy\s*\(", code)
    q("première instruction = strategy(...)", bool(m))
    mr = re.search(r"(?m)^\s*strategy\s*\(", src)
    decl = ""
    if mr:
        fin = src.find("\n)", mr.start())
        if fin == -1:
            fin = src.find(");", mr.start())
            fin = fin + 2 if fin != -1 else len(src)
        decl = src[mr.start(): fin + 2]
        decl = decl[: decl.rfind(")") + 1]
    for kw in ['instrument="perps"', 'funding="data"', "leverage=10",
               "maintenanceMarginPercent=0.5", "makerFeePercent",
               "takerFeePercent", "initialCapital=100", "slippageBps=2",
               'fillModel="pessimistic"', "pyramiding=1"]:
        q(f"strategy(): {kw}", kw in decl)
    q("strategy(): commissionPercent absent (perps uniquement)",
      "commissionPercent" not in decl)

    for op, cl, nom in [("{", "}", "accolades"), ("(", ")", "parenthèses"),
                        ("[", "]", "crochets")]:
        q(f"équilibre {nom} ({code.count(op)}/{code.count(cl)})",
          code.count(op) == code.count(cl))
    q("aucune tabulation", "\t" not in src)
    q("pas d'espace en fin de ligne", not re.search(r"(?m)[ \t]+$", src))

    appels = set(re.findall(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(", code))
    connus = BUILTINS | {"if", "else", "for", "while", "switch", "func",
                         "return"}
    inconnus = {c for c in appels if c not in connus}
    q(f"aucune fonction inconnue ({sorted(inconnus) or 'clean'})",
      not inconnus)
    q("adx() natif absent du code (proxy NDD documenté utilisé)",
      "adx(" not in code)

    # Parseur d'inputs à équilibrage de parenthèses (les inputs sont multi-
    # lignes, sans point-virgule final ; le code est stripped des chaînes).
    inputs = []
    for m in re.finditer(r"(?m)^var\s+(\w+)\s*=\s*input\(", code):
        nom = m.group(1)
        i = m.end()
        profondeur, j = 1, i
        while j < len(code) and profondeur > 0:
            if code[j] == "(":
                profondeur += 1
            elif code[j] == ")":
                profondeur -= 1
            j += 1
        inputs.append((nom, code[i:j - 1]))
    q(f"inputs déclarés: {len(inputs)} (>= 20)", len(inputs) >= 20)
    mauvais = [n for n, b in inputs
               if 'name="' not in b or 'type="' not in b
               or "defaultValue=" not in b]
    q(f"inputs name/type/defaultValue complets {mauvais or ''}", not mauvais)
    declares = {n for n, _ in inputs}
    used_inputs = set(re.findall(r"(?<![\w.])(\w+)(?![\w(])", code))
    non_utilises = {d for d in declares
                    if len(re.findall(rf"\b{d}\b", code)) < 2}
    q(f"tous les inputs utilisés {sorted(non_utilises) or ''}",
      not non_utilises)
    itypes = re.findall(r'input\([^;]*?type="(\w+)"', code)
    q("types d'input valides",
      set(itypes) <= {"number", "int", "float", "boolean", "string", "select",
                      "multiSelect", "source", "color", "color[]", "slider",
                      "timeframe", "session", "symbol", "text"})

    stypes = re.findall(r'source\("(\w+)"', code) + \
        re.findall(r"(?<![a-z_])(buy_sell_volume|ohlcv)\s*\(", code)
    q(f"types de sources valides {sorted(set(stypes))}",
      set(stypes) <= SRC_TYPES)
    nb_sources = len({("ohlcv", None), ("funding_rate", None),
                      ("buy_sell_volume", None), ("htf", "4h"),
                      ("htf", "1d"), ("request", "BTCUSDT:1d")})
    q(f"budget sources = {nb_sources} <= 10", nb_sources <= 10)

    # timeframes : TOUJOURS sur le source brut (les chaînes sont vidées dans
    # le code stripped).
    tfs = re.findall(r'htf\([^)]*timeframe="([^"]+)"', src) + \
        re.findall(r'request\("[^"]+",\s*"([^"]+)"', src)
    q(f"htf/request timeframes valides {sorted(set(tfs))}",
      all(TF_RE.match(t) for t in tfs))

    entry_ids = set(re.findall(r'strategy\.entry\("(\w+)"', src))
    attends = {"A1L", "A1S", "A2L", "A2S", "A3L", "A3S", "A4L", "A4S",
               "A6L", "A6S"}
    q(f"entry ids = {sorted(entry_ids)} (10 alphas attendus)",
      entry_ids == attends)
    exit_froms = set(re.findall(r"strategy\.exit\([^;]*?fromEntry=(\w+)",
                                code))
    q("exit fromEntry = activeId (variable persist)", exit_froms == {"activeId"})
    exits = []
    for m in re.finditer(r"strategy\.exit\(", code):
        i = m.end()
        profondeur, j = 1, i
        while j < len(code) and profondeur > 0:
            if code[j] == "(":
                profondeur += 1
            elif code[j] == ")":
                profondeur -= 1
            j += 1
        exits.append(code[i:j - 1])
    q(f"strategy.exit x{len(exits)} (TP1+TP2+SL attendus) — chaque jambe "
      "a limit/stop",
      len(exits) == 3 and all(("limit=" in e or "stop=" in e) for e in exits))
    qps = set(re.findall(r"qtyPercent=(\d+)", code))
    q(f"échelle qtyPercent = {sorted(qps)} (50/25/100 attendu, TP2=25 "
      "après fix « targeted quantity »)", qps == {"50", "25", "100"})
    q("jambe TP1 armée seulement avant service",
      "if (!tp1Done) {" in src and 'strategy.exit("TP1"' in src)
    q("jambe TP2 armée seulement après TP1",
      "if (tp1Done && !tp2Done) {" in src)
    q("closeAll au verrou de mission", "strategy.closeAll()" in src)
    nb_close = len(re.findall(r"strategy\.close\(", src))
    q(f"sortie défensive strategy.close x{nb_close} (1 close générique "
      "pour les 10 ids, branches defLong/defShort)", nb_close == 1)

    # Sizing PAT complet (allocation G4 par alpha, certifiée MC v11 corrélé)
    for motif in ["gDD", "gPace", "fAbs",
                  "math.min(riskMainA1 / 100.0 * gDD * gPace, fAbs)",
                  "math.min(riskOther / 100.0 * gDD * gPace, fAbs)",
                  "math.min((isAlt ? riskSatA3 : riskMainA3) / 100.0 * gDD * gPace, fAbs)",
                  "math.min((isAlt ? riskSatA4 : riskMainA4) / 100.0 * gDD * gPace, fAbs)",
                  "eq * levMax / px", "targetEq", "lock"]:
        q(f"sizing PAT : {motif}", motif in code)
    for fa in ("fA1", "fA2", "fA3", "fA4", "fA6"):
        n_qty = len(re.findall(rf"eq \* {fa} / \(", code))
        q(f"sizing PAT : {fa} -> 2 entrées (long+short) = {n_qty}", n_qty == 2)
    n_fused = len(re.findall(r"fUsed = fA\d", code))
    q(f"sizing PAT : fUsed alimenté x{n_fused} (10 entrées)", n_fused == 10)
    q("sizing PAT : alerte sur fUsed (mise du signal réel)",
      "fUsed * 100.0" in code)
    q("sizing PAT : ancien riskPct global supprimé", "riskPct" not in code)

    # Séries au niveau racine (anti-repaint) : aucune déclaration indentée
    series_indent = [l for l in lignes
                     if re.match(r"^\s+(timeseries|persist)\s", l)]
    q(f"séries/état déclarés au niveau racine ({len(series_indent)} indentés)",
      not series_indent)
    pers = re.findall(r"(?m)^\s*persist\s+(\w+)", code)
    q(f"persist x{len(pers)} — déclarations uniques", len(pers) == len(set(pers)))

    q("alert(message=, condition=) à la racine",
      "alert(message=" in src and "condition=" in src)
    q("placeholders format() {0}..{4} (idiome officiel)",
      re.search(r'format\("[^"]*\{0\}', src) is not None)
    q("alertcondition(condition, title, message) x2",
      len(re.findall(r"alertcondition\(", src)) == 2)
    q("plotShape location belowBar/aboveBar",
      'location="belowBar"' in src and 'location="aboveBar"' in src)

    echecs = 0
    for ok, label in msgs:
        if not ok:
            echecs += 1
            print(f">>FAIL {label}")
        else:
            print(f"  PASS {label}")
    print(f"\n{'=' * 55}")
    print(f"RÉSULTAT : {'PASS — 0 échec' if echecs == 0 else f'{echecs} échec(s)'}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
