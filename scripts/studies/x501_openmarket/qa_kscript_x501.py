#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QA syntaxique des scripts kScript x501 — validation statique contre la doc officielle."""
import re, sys, json
from pathlib import Path

HERE = Path(__file__).resolve().parent

FILES = [
    HERE / "Operation_x501_Signature_H1.ks",
    HERE / "Operation_x501_Signature_H4.ks",
    HERE / "Operation_x501_Alpha2_Cascade_Financement_H4.ks",
    HERE / "Operation_x501_Alpha3_Eruption_Volatilite_H4.ks",
    HERE / "Operation_x501_Alpha4_Confluence_MTF_H4.ks",
]

# Whitelist issue des pages officielles scrapées (ta-library, strategy-functions,
# data-sources, plotting, math-functions, utility, core-variables)
BUILTINS = {
    # TA
    "sma","ema","alma","swma","wma","vwma","hma","rma","rsi","wpr","cmo","tsi","macd",
    "stoch","cci","mfi","change","roc","mom","adx","psar","supertrend","tr","atr","hl2",
    "hlc3","ohlc4","hlcc4","bb","keltner","stdev","stddev","variance","obv","vwap","cum",
    "correlation","median","percentile","linreg","highest","lowest","highestbars","lowestbars",
    "pivothigh","pivotlow","valuewhen","barssince","rising","falling","crossover","crossunder",
    "cross","fixnan","isna","nz","ichimoku",
    # strategy
    "strategy","input","plotLine","plotShape","plotTable","plotChar","fillBetween",
    "strategy.entry","strategy.exit","strategy.close","strategy.closeAll",
    "strategy.cancel","strategy.cancelAll","strategy.positionSize",
    "strategy.positionAvgPrice","strategy.equity","strategy.openProfit",
    "strategy.netProfit","strategy.closedTradeCount","strategy.winTradeCount",
    "strategy.lossTradeCount","strategy.maxDrawdown",
    # sources directes
    "ohlcv","buy_sell_volume","source","htf","ltf","request","requestBars",
    # orderbook / vp
    "sumBids","sumAsks","maxBidAmount","maxAskAmount","minBidAmount","minAskAmount",
    "vpBuy","vpSell","vpDelta","vpPoc",
    # math
    "math.abs","math.max","math.min","math.sqrt","math.pow",
    # temps
    "time","timenow","hour","session","sessionName",
}
GLOBALS = {"currentSymbol","currentExchange","currentCoin","barIndex","isLastBar",
           "isConfirmed","isFirst","na","true","false"}

# Paramètres nommés (kwargs) des builtins + mots-clés du langage
KWARGS = {"title","position","axis","customTitle","format","maxBarsBack","initialCapital",
    "currency","commissionPercent","slippageBps","slippageModel","qtyType","qtyValue",
    "pyramiding","fillModel","instrument","leverage","maintenanceMarginPercent",
    "makerFeePercent","takerFeePercent","funding","onLiquidation","name","type",
    "defaultValue","label","constraints","group","options","symbol","exchange","coin",
    "asset","delta","timeframe","opts","mode","offset","bars","period","mult","factor",
    "atrPeriod","source","id","direction","qty","limit","stop","ocaName","comment",
    "fromEntry","profit","loss","trailPoints","trailOffset","value","colors","colorIndex",
    "width","desc","fill","smooth","showPriceDisplay","shape","glow","data","headerRow",
    "headerColumn","x","y","priceIndex","anchor","n","constant","start","increment",
    "maxValue","depthPct","fastPeriod","slowPeriod","signalPeriod","kPeriod","smoothK",
    "periodD","periodK","conversionPeriod","basePeriod","laggingSpanPeriod",
    "displacement","short","long"}
LANG = {"var","persist","timeseries","if","else","func","return","for","while","switch",
        "import","as","static","break","continue"}
SRC_TYPES = {"ohlcv","open_interest","buy_sell_volume","trade_volume_by_size","funding_rate",
             "liquidations","orderbook","cme_oi","deribit_implied_volatility",
             "deribit_volatility_index","skew","etf_premium_rate","etf_holding",
             "options_volume","options_open_interest","etf_flow","ethena_positions",
             "long_short_ratio","binance_treasury_balance","volume_profile"}
SHAPES = {"circle","triangle","cross","diamond"}
TF_RE = re.compile(r"^\d+(m|h|d)$|^1[DWMQY]$")

def strip_comments_strings(src: str):
    """Retourne le code sans commentaires (// et /* */) ni contenu de chaînes."""
    out, i, n = [], 0, len(src)
    in_str = None
    while i < n:
        c = src[i]
        nxt = src[i+1] if i+1 < n else ""
        if in_str:
            if c == "\\":
                i += 2; continue
            if c == in_str:
                in_str = None
            out.append(" " if in_str else c)
            i += 1; continue
        if c in "\"'":
            in_str = c; out.append(c); i += 1; continue
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and nxt == "*":
            i += 2
            while i+1 < n and not (src[i] == "*" and src[i+1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c); i += 1
    return "".join(out)

def qadir(msgs, label, cond):
    msgs.append(("OK" if cond else "FAIL", label))

def check_file(path: Path):
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    code = strip_comments_strings(src)
    msgs = []
    print(f"\n=== {path.name} ===")

    # 1. version
    qadir(msgs, "1re ligne = //@version=3", lines and lines[0].strip() == "//@version=3")

    # 2. strategy() = première instruction du code
    m = re.search(r"(?m)^\s*(strategy|define)\s*\(", code)
    qadir(msgs, "première instruction = strategy(...)", bool(m) and m.group(1) == "strategy")
    # decl lu dans le SOURCE BRUT (les chaînes y sont intactes)
    mr = re.search(r"(?m)^\s*strategy\s*\(", src)
    decl = src[mr.start(): src.index(");", mr.start())] if mr else ""

    # 3. paramètres broker clés
    for kw in ["instrument=\"perps\"", "funding=\"data\"", "leverage=10",
               "maintenanceMarginPercent=0.5", "makerFeePercent", "takerFeePercent",
               "initialCapital=100", "slippageBps=2"]:
        qadir(msgs, f"strategy(): {kw}", kw in decl)
    qadir(msgs, "strategy(): commissionPercent absent (spot-only)",
          "commissionPercent" not in decl)

    # 4. équilibre des blocs (hors chaînes/commentaires)
    for op, cl, name in [("{","}","accolades"), ("(",")","parenthèses"), ("[","]","crochets")]:
        qadir(msgs, f"équilibre {name}", code.count(op) == code.count(cl))

    # 5. pas de tabulations, pas d'espaces en fin de ligne
    qadir(msgs, "aucune tabulation", "\t" not in src)
    qadir(msgs, "pas d'espace en fin de ligne", not re.search(r"(?m)[ \t]+$", src))

    # 6. fonctions inconnues ?
    calls = set(re.findall(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(", code))
    known = BUILTINS | {"if","else","for","while","switch","func","return"}
    unknown = {c for c in calls if c not in known}
    # les appels de méthode .filter/.map/.reduce/.cells sont légitimes
    unknown -= {"filter","map","reduce"}
    qadir(msgs, f"aucune fonction inconnue ({sorted(unknown) if unknown else 'clean'})",
          not unknown)

    # 7. inputs bien formés + collecte
    inputs = re.findall(r"var\s+(\w+)\s*=\s*input\(([^;]*)\);", code)
    qadir(msgs, f"inputs déclarés: {len(inputs)}", len(inputs) >= 20)
    bad_inputs = []
    for name, body in inputs:
        if 'name="' not in body or 'type="' not in body or "defaultValue=" not in body:
            bad_inputs.append(name)
    qadir(msgs, f"inputs name/type/defaultValue complets {bad_inputs or ''}", not bad_inputs)
    declared = {n for n, _ in inputs}

    # types d'input valides
    itypes = re.findall(r'input\([^;]*?type="(\w+)"', code)
    qadir(msgs, "types d'input valides",
          set(itypes) <= {"number","int","float","boolean","string","select","multiSelect",
                          "source","color","color[]","slider","timeframe","session","symbol","text"})

    # 8. sources : types valides + budget
    stypes = re.findall(r'source\("(\w+)"', code) + re.findall(r'(?<![a-z_])(buy_sell_volume|ohlcv)\s*\(', code)
    qadir(msgs, f"types de sources valides {sorted(set(stypes))}", set(stypes) <= SRC_TYPES)
    qadir(msgs, "budget sources <= 10 (4 souscrites ici)", len(set(stypes)) <= 10)

    # 9. htf : timeframes valides (source brut)
    tfs = re.findall(r'htf\([^)]*timeframe="([^"]+)"', src)
    qadir(msgs, f"htf timeframes valides {tfs}", all(TF_RE.match(t) for t in tfs))

    # 10. identifiants d'ordres cohérents (source brut)
    entry_ids = set(re.findall(r'strategy\.entry\("(\w+)"', src))
    exit_froms = set(re.findall(r'strategy\.exit\([^;]*?fromEntry=(\w+)', code))
    qadir(msgs, f"entry ids {sorted(entry_ids)} (L,S attendus)", entry_ids == {"L","S"})
    qadir(msgs, "exit fromEntry = variable entryId", exit_froms == {"entryId"})

    # 11. exit legs: tout exit a au moins un de limit/stop/profit/loss/trail
    exits = re.findall(r"strategy\.exit\(([^;]*)\);", code)
    qadir(msgs, f"strategy.exit x{len(exits)} — chaque leg a limit/stop",
          all(("limit=" in e or "stop=" in e) for e in exits))

    # 12. plotShape shapes valides (source brut)
    shapes = set(re.findall(r'plotShape\([^;]*?shape="(\w+)"', src))
    qadir(msgs, f"plotShape shapes {sorted(shapes)}", shapes <= SHAPES)

    # 13. identificateurs non déclarés (heuristique : LHS connus + builtins + globals)
    assigned = set(re.findall(r"(?m)^\s*(?:var|persist|timeseries)\s+(\w+)", code))
    assigned |= set(re.findall(r"(?m)^\s*(?:var|persist|timeseries)\s+\[[\w,\s]+\]\s*=", code) and [])
    destructure = re.findall(r"\[([\w\s,]+)\]\s*=", code)
    for grp in destructure:
        assigned |= {t.strip() for t in grp.split(",") if t.strip()}
    assigned |= {m for m in re.findall(r"(?m)^\s{2}(\w+)\s*=[^=]", code)}
    used_ids = set(re.findall(r"\b([a-z][A-Za-z0-9_]*)\b(?=\s*[.\[])", code))
    plain_ids = set(re.findall(r"(?<![\w.])([a-z][A-Za-z0-9_]*)\b(?!\s*\()", code))
    members = {t for t in re.findall(r"\.(\w+)", code)}
    suspects = {i for i in plain_ids
                if i not in assigned and i not in known and i not in GLOBALS
                and i not in KWARGS and i not in LANG and i not in members
                and i not in {"USD","math","step","USD","onchart","offchart","perps","spot","data","off",
                "continue","halt","fixed","percentOfEquity","cash","pessimistic",
                "pathHeuristic","day","week","month","confirmed","developing",
                "number","int","float","boolean","string","text","slider","select",
                "color","top_right","top_left","bottom_right","bottom_left"}}
    qadir(msgs, f"identifiants non déclarés: {sorted(suspects) if suspects else 'aucun'}",
          not suspects)

    # 14. persist vs var : les persist ne doivent pas être ré-déclarés
    pers = re.findall(r"(?m)^\s*persist\s+(\w+)", code)
    qadir(msgs, f"persist x{len(pers)} — déclarations uniques", len(pers) == len(set(pers)))

    # 15. risk guard : formule de sizing présente
    qadir(msgs, "sizing = risque$ / distance au stop", "riskUsdL / distL" in code and "riskUsdS / distS" in code)
    qadir(msgs, "plafond levier effectif", "maxEffLev" in code)
    qadir(msgs, "coupe-circuits (jour/semaine/absolu)",
          all(k in code for k in ["dailyStop","weeklyStop","killDD","halted"]))

    fails = 0
    for status, label in msgs:
        mark = "  PASS " if status == "OK" else ">>FAIL "
        if status != "OK":
            fails += 1
        print(f"{mark}{label}")
    return fails

if __name__ == "__main__":
    total = 0
    for f in FILES:
        total += check_file(f)
    print(f"\n{'='*50}\nRESULTAT GLOBAL : {'PASS — 0 échec' if total == 0 else f'{total} échec(s)'}")
    sys.exit(1 if total else 0)
