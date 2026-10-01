#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QA anti-bug des VAGUES 1-2 kScript x501 (docs/27) — validation statique
contre la doc kScript v3 scrapée (78 pages, research_ks/pages/).
Fichiers couverts :
  - Operation_x501_Signature_H1_RI.ks   (vague 1 : régime institutionnel)
  - x501_observe_regime.ks              (vague 1 : observe des 7 flux)
  - Operation_x501_Absorption_H1.ks     (vague 2 : absorption orderbook)
Chemins relatifs au script (portable repo), stdlib pure."""
import re
import sys
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
RI = DOSSIER / "Operation_x501_Signature_H1_RI.ks"
OBS = DOSSIER / "x501_observe_regime.ks"
ABS = DOSSIER / "Operation_x501_Absorption_H1.ks"

# Whitelist issue des pages officielles scrapées (data-sources, orderbook-
# functions, ta-library, math-functions, strategy-functions, alerts)
BUILTINS = {
    "sma", "ema", "alma", "swma", "wma", "vwma", "hma", "rma", "rsi", "wpr",
    "cmo", "tsi", "macd", "stoch", "cci", "mfi", "change", "roc", "mom", "adx",
    "psar", "supertrend", "tr", "atr", "hl2", "hlc3", "ohlc4", "hlcc4", "bb",
    "keltner", "stdev", "stddev", "variance", "obv", "vwap", "cum", "sum",
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
    "sumBids", "sumAsks", "maxBidAmount", "maxAskAmount",
    "minBidAmount", "minAskAmount",
    "math.abs", "math.max", "math.min", "math.sqrt", "math.pow", "math.sign",
    "math.floor", "math.ceil", "math.round", "math.log", "math.exp",
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


def count_sources(code):
    """Nombre de souscriptions distinctes (timeseries = ohlcv|source|bsv)."""
    n = len(re.findall(r"(?m)^timeseries\s+\w+\s*=\s*(ohlcv|source|buy_sell_volume)\s*\(", code))
    return n


def check_commun(nom, src, msgs):
    """Checks génériques à tout fichier .ks du domaine."""
    code = strip_comments_strings(src)
    lignes = src.splitlines()

    def q(label, cond):
        msgs.append((bool(cond), f"[{nom}] {label}"))

    q("1re ligne = //@version=3", lignes and lignes[0].strip() == "//@version=3")
    for op, cl, nm in [("{", "}", "accolades"), ("(", ")", "parenthèses"),
                       ("[", "]", "crochets")]:
        q(f"équilibre {nm} ({code.count(op)}/{code.count(cl)})",
          code.count(op) == code.count(cl))
    q("aucune tabulation", "\t" not in src)
    q("pas d'espace en fin de ligne", not re.search(r"(?m)[ \t]+$", src))
    appels = set(re.findall(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(", code))
    connus = BUILTINS | LANG | {"if", "else", "for", "while", "switch", "func",
                                "return"}
    inconnus = {c for c in appels if c not in connus}
    q(f"aucune fonction inconnue ({sorted(inconnus) or 'clean'})", not inconnus)
    # types de sources = tous dans la table officielle (doc data-sources)
    types_us = set(re.findall(r'source\(\s*"([a-z_]+)"', src))
    q(f"types de sources officiels ({sorted(types_us)})",
      types_us <= SRC_TYPES)
    # args symbol/coin/asset/exchange : literals, inputs, current* uniquement
    # (doc : env identifiers, PAS de variables calculées)
    args = re.findall(r"(symbol|coin|asset|exchange)=([A-Za-z_][\w]*)", code)
    mauvais = [a for a in args if a[1] not in GLOBALS and
               not re.match(r"^(etfSymbol|optExchange|skewDelta)$", a[1])]
    q(f"args source() = literals/inputs/env ({mauvais or 'clean'})", not mauvais)
    # série/état déclarés au niveau racine
    series_indent = [l for l in lignes
                     if re.match(r"^\s+(timeseries|persist)\s", l)]
    q(f"séries/état au niveau racine ({len(series_indent)} indentés)",
      not series_indent)
    pers = re.findall(r"(?m)^\s*persist\s+(\w+)", code)
    q(f"persist x{len(pers)} — déclarations uniques",
      len(pers) == len(set(pers)))
    # budget sources (10 slots pondérés)
    n_src = count_sources(code)
    q(f"budget sources {n_src} <= 10", n_src <= 10)
    # pré-enregistrement gravé dans l'en-tête
    q("en-tête : pré-enregistrement documenté", "PRÉ-ENREGISTRÉ" in src)
    q("en-tête : DOCUMENT ÉDUCATIF", "DOCUMENT ÉDUCATIF" in src)
    return code


def main():
    msgs = []

    def q(label, cond):
        msgs.append((bool(cond), label))

    # ---------------- VAGUE 1 : Signature H1 RI (stratégie) -----------------
    src = RI.read_text(encoding="utf-8")
    code = check_commun("RI", src, msgs)
    code_ri = strip_comments_strings(src)

    q("[RI] strategy(...) déclarée", "strategy(" in code_ri)
    for kw in ['instrument="perps"', 'funding="data"', "leverage=10",
               "makerFeePercent=0.018", "takerFeePercent=0.045",
               "initialCapital=100", "slippageBps=2",
               'fillModel="pessimistic"']:
        q(f"[RI] strategy(): {kw}", kw in src)
    # les 5 flux institutionnels (vague 1) — sur le texte BRUT (1er arg = string)
    for t in ["etf_flow", "cme_oi", "deribit_volatility_index", "skew",
              "long_short_ratio"]:
        q(f"[RI] source premium {t} branchée", f'source("{t}"' in src)
    # no-repaint : les buckets quotidiens complétés uniquement ([1] et avant)
    q("[RI] etfD.value[0] JAMAIS lu (no-repaint)",
      "etfD.value[0]" not in code_ri)
    q("[RI] cmeD.close[0] JAMAIS lu (no-repaint)",
      "cmeD.close[0]" not in code_ri)
    q("[RI] skwD.one_week[0] JAMAIS lu (no-repaint)",
      "skwD.one_week[0]" not in code_ri)
    q("[RI] etfD.value[1..3] lus (hier et avant)",
      "etfD.value[1]" in code_ri and "etfD.value[3]" in code_ri)
    q("[RI] cmeR = close[1]/close[4] (3 j complétés)",
      "cmeD.close[1]" in code_ri and "cmeD.close[4]" in code_ri)
    q("[RI] skew : dérive [1]-[6] (5 buckets)",
      "skwD.one_week[1]" in code_ri and "skwD.one_week[6]" in code_ri)
    q("[RI] long_short_ratio : PAS de membre .time utilisé",
      "lsr.time" not in code_ri)
    # 5 composantes écrêtées + poids égaux
    q("[RI] 5 composantes clampées (math.max(-1, math.min(1, x)))",
      len(re.findall(r"math\.max\(-1,\s*math\.min\(1,", code_ri)) == 5)
    q("[RI] score = moyenne des 5 (poids égaux, pré-enregistré dur)",
      ") / 5" in code_ri)
    # fail-open pré-enregistré
    q("[RI] fail-open : riReady == false rend le filtre transparent",
      code_ri.count("riReady == false") == 2)
    q("[RI] seuil RI symétrique long/short",
      "riScore >= riMin" in code_ri and "riScore <= -riMin" in code_ri)
    q("[RI] A/B : useRiFilter désactivable",
      "useRiFilter == false" in code_ri)
    # squelette Signature préservé (comparabilité)
    for kw in ["regimeLong", "zoneTouchLong", "cvdUp", "bullBar",
               "fundingOkLong", "breakersOk", "flushNow", "liqMult"]:
        q(f"[RI] moteur Signature préservé : {kw}", kw in code_ri)
    q("[RI] coupe-circuit -25% (closeAll)",
      "halted == 1 && flat == false" in code_ri and
      "strategy.closeAll" in code_ri)
    q("[RI] sizing = risque fixe plafonné levier",
      "riskPct / 100" in code_ri and "maxEffLev / trade.close" in code_ri)
    q("[RI] alert() RI flip", "alert(" in code_ri)
    # 9 sources attendues (4 Signature + 5 premium)
    q("[RI] 9 souscriptions (4 Signature + 5 premium)",
      count_sources(code_ri) == 9)

    # ---------------- VAGUE 1 : observe régime (indicateur) -----------------
    src = OBS.read_text(encoding="utf-8")
    code_obs = check_commun("OBS", src, msgs)

    q("[OBS] define(...) en tête (indicateur, PAS strategy)",
      "define(" in code_obs and "strategy(" not in code_obs)
    for t in ["etf_flow", "etf_holding", "cme_oi",
              "deribit_volatility_index", "skew", "long_short_ratio",
              "binance_treasury_balance", "options_open_interest"]:
        q(f"[OBS] source premium {t} branchée", f'source("{t}"' in src)
    q("[OBS] 9 souscriptions (spine + 8 premium)",
      count_sources(code_obs) == 9)
    q("[OBS] buckets lents : jamais [0]",
      "etfD.value[0]" not in code_obs and "cmeD.close[0]" not in code_obs
      and "skwD.one_week[0]" not in code_obs)
    q("[OBS] même formule RI que la version RI (/5)",
      ") / 5" in code_obs)
    q("[OBS] plotTable de disponibilité par flux",
      "plotTable(" in code_obs and '"flux"' in src)
    q("[OBS] verdict isna() par flux (>= 7)",
      len(re.findall(r"isna\(", code_obs)) >= 7)
    q("[OBS] long_short_ratio : PAS de .time", "lsr.time" not in code_obs)
    q("[OBS] alert() bascule de quadrant", "alert(" in code_obs)
    q("[OBS] skew : membre one_week (jamais one_month mal épelé ici)",
      "skwD.one_week" in code_obs)

    # ---------------- VAGUE 2 : absorption orderbook (stratégie) ------------
    src = ABS.read_text(encoding="utf-8")
    code_abs = check_commun("ABS", src, msgs)

    q("[ABS] strategy(...) déclarée", "strategy(" in code_abs)
    for kw in ['instrument="perps"', 'funding="data"',
               "makerFeePercent=0.018", "takerFeePercent=0.045",
               "initialCapital=100", "slippageBps=2"]:
        q(f"[ABS] strategy(): {kw}", kw in src)
    q("[ABS] source orderbook branchée", 'source("orderbook"' in src)
    # les 4 fonctions natives (0 usage avant la vague 2)
    for fn in ["maxBidAmount(", "maxAskAmount(", "sumBids(", "sumAsks("]:
        q(f"[ABS] fonction native {fn} utilisée", fn in code_abs)
    q("[ABS] l'orderbook array-celled n'est JAMAIS lu en direct",
      "book.bids" not in code_abs and "book.asks" not in code_abs)
    q("[ABS] mur = outlier de sa propre histoire (wallMult x bidTyp)",
      "wallBid >= wallMult * bidTyp" in code_abs and
      "wallAsk >= wallMult * askTyp" in code_abs)
    q("[ABS] attaque = volume taker x sa moyenne (atkMult)",
      "bsv.sell >= atkMult * sellTyp" in code_abs and
      "bsv.buy >= atkMult * buyTyp" in code_abs)
    q("[ABS] tenue : écrasement intrabar borné (maxDefPct)",
      "maxDefPct" in code_abs and "(trade.open - trade.low)" in code_abs)
    q("[ABS] flux net bascule (flowEma)",
      "flowEma > 0" in code_abs and "flowEma < 0" in code_abs)
    q("[ABS] déséquilibre de carnet (imbMin)",
      "imb >= imbMin" in code_abs and "imbRev >= imbMin" in code_abs)
    q("[ABS] division protégée par math.max(x, 1e-9)",
      code_abs.count("1e-9") >= 3)
    q("[ABS] coupe-circuit -25% (closeAll)",
      "halted == 1 && flat == false" in code_abs and
      "strategy.closeAll" in code_abs)
    q("[ABS] sizing = risque fixe plafonné levier",
      "riskPct / 100" in code_abs and "maxEffLev / trade.close" in code_abs)
    q("[ABS] TP1/TP2/runner (3 strategy.exit)",
      code_abs.count("strategy.exit(") >= 3)
    q("[ABS] alert() mur géant", "alert(" in code_abs)
    q("[ABS] 4 souscriptions (spine + orderbook + bsv + funding)",
      count_sources(code_abs) == 4)
    # limite d'historique orderbook documentée (honnêteté)
    q("[ABS] limite de profondeur orderbook documentée en en-tête",
      "profondeur d'historique orderbook" in src)

    echecs = 0
    for ok, label in msgs:
        if not ok:
            echecs += 1
            print(f">>FAIL {label}")
        else:
            print(f"  PASS {label}")
    print(f"\n{'=' * 55}")
    print(f"RÉSULTAT : {'PASS — 0 échec' if echecs == 0 else f'{echecs} échec(s)'} "
          f"({len(msgs)} contrôles)")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
