#!/usr/bin/env python3
"""ETUDE (one-shot, mission T16) : la table REGIME x STRATEGIE sur la
granularite 15m PROFONDE (backfill T6 : BTC 178k / ETH 177.5k / SOL 177.3k
barres 15m, 2021-09 -> 2026-09) — les edges existent-ils a la granularite
intraday que les 4 ans revelent ?

Question (mission T16) : T7 (scripts/studies/aster_deep_regimes.py,
reports/aster_deep_regimes.md) a juge les 6 strategies CAMPAGNE sur les 1h
profondes (44.3-44.5k barres) : aucun edge regime-independant a 1x frais
taker, momentum = edge de cycle 2023-2024, MR = WR invariant mais PnL tue par
le RR, decay generale 2025-2026. Ici on rejoue EXACTEMENT les memes configs
(REF = meilleure lane nightly du 30/09 + variations V1-V3, re-importees du
module T7) sur les 15m profondes :

  - memes parametres EN BARRES -> les constantes de temps sont 4x plus
    courtes (EMA 20/100/200 barres = 5h/25h/50h au lieu de 20h/100h/200h).
    C'EST le test intraday : la meme logique, le tape 4x plus rapide.
  - la fenetre de decouverte de la campagne = 2026-06-06 -> (3 000 dernieres
    1h de la nightly ; couvre largement les 3 000 dernieres 15m = 31 jours).
    Tout le deep 2021-09 -> 2026-05 est un OOS temporel strict.

Harness : strategies SONT celles de la campagne (backend/services/
backtest_v2/strategies/*), signal barre i -> execution a l'OPEN de i+1.
LE FIX DU HARNAIS EST ACTIF (commit b825da9) : stops + frais (4 bps taker par
fill) bookes dans bar_ret, mark-to-market du dernier prix -> l'equite du
validateur (sharpe IS/OOS walk-forward, DD, gates) est HONNETE. Les stats de
ce rapport restent calculees sur le FLUX DE TRADES (t7.regime_stats, couche
identique a T7) pour la comparaison 1h/15m manche par manche.

Funding : MODELE documente de T7, re-importe (constant par regime, bps/8h ;
periode connue = moyennes REELLES Aster). funding_fade = serie injectee
(INDICATIF, artefact documente) ; funding_carry = stub + re-resolution du sens
par regime (experience supplementaire).

Reutilisation du module T7 (import scripts.studies.aster_deep_regimes) :
REGIMES, CONFIGS, STRAT_MODULES, ARTEFACT_STRATS, regime_of, regime_stats,
empty_regime_stats, _fracs, install_funding_stub, injected_fade_series.

AUCUNE ecriture hors reports/ ; DB lue en mode=ro. Stdlib pure.

Usage :
    .venv/bin/python scripts/studies/aster_15m_regimes.py                # run
    .venv/bin/python scripts/studies/aster_15m_regimes.py --write        # + md
    .venv/bin/python scripts/studies/aster_15m_regimes.py --symbol BTCUSDT \
        --strategy momentum --write                                      # lane
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_klines import init_db, load_bars  # noqa: E402
import scripts.studies.aster_deep_regimes as t7  # noqa: E402
from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.engine import (  # noqa: E402
    CampaignConfig,
    evaluate_one,
)
from backend.services.backtest_v2.gates import GateConfig  # noqa: E402
from backend.services.backtest_v2 import strategies as strat_pkg  # noqa: E402
from backend.services.backtest_v2.strategies import funding_carry as fc  # noqa: E402
from backend.services.backtest_v2.costs import FundingRate  # noqa: E402

KLINES_DB = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "aster_15m_regimes.md"
RAW = ROOT / "reports" / "aster_15m_regimes_raw.json"
T7_RAW = ROOT / "reports" / "aster_deep_regimes_raw.json"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVAL = "15m"

# Fenetre de DECOUVERTE : celle de la derniere campagne nightly (3 000
# dernieres 1h = 2026-06-06 ->). A 15m elle couvre ~11 500 barres ; les
# "3 000 dernieres 15m" (31 jours) sont incluses dedans.
DISCOVERY_START = t7.DISCOVERY_START  # "2026-06-06"

CONFIGS = t7.CONFIGS
STRAT_MODULES = t7.STRAT_MODULES
ARTEFACT_STRATS = t7.ARTEFACT_STRATS


# ------------------------------------------------------------------- moteur

def run_eval(strat: str, cfg_name: str, params: dict, symbol: str,
             bars: list[Bar], gate_cfg: GateConfig) -> dict:
    """Une lane 15m : evaluation harnais (equite HONNETE post-fix b825da9) +
    stats par regime sur le flux de trades (couche T7, comparable 1h/15m)."""
    p = dict(params)
    p["symbol"] = symbol
    if strat == "funding_fade":
        p["funding_bps_series"] = t7.injected_fade_series(bars, symbol)
    evaluate = strat_pkg.REGISTRY[strat][0]
    ev = evaluate(p, bars)
    identity = strat_pkg.make_identity(strat, p, symbol=symbol, interval=INTERVAL)
    cfg = CampaignConfig(run_id=f"study15m-{strat}-{symbol}-{cfg_name}",
                         data_snapshot_id="deep-2021-2026-backfill-T6-15m",
                         gate_config=gate_cfg)
    metrics, gate, _bench, extra = evaluate_one(identity, ev, bars, cfg)
    entries = ev.blob.get("entries") or []
    reasons = ev.blob.get("exit_reasons") or []
    if strat == "volatility_harvesting":
        entries = [(i, 1) for i in (ev.blob.get("harvest_bars") or [])]
        reasons = ["take"] * len(entries)
    stop_frac, take_frac = t7._fracs(params)
    by_regime = {}
    for name, a, b in t7.REGIMES:
        st = t7.regime_stats(bars, list(ev.bar_returns_per_bar), entries,
                             reasons, list(ev.trade_returns), stop_frac,
                             take_frac, t7._date_ms(a),
                             t7._date_ms(b) + t7.DAY_MS - 1)
        by_regime[name] = st or t7.empty_regime_stats()
    return {
        "strategy": strat, "config": cfg_name, "symbol": symbol,
        "closed_trades": ev.closed_trades,
        "sharpe_is": extra["walkforward"]["sharpe_is"],
        "sharpe_oos": extra["walkforward"]["sharpe_oos"],
        "oos_is_ratio": extra["walkforward"]["oos_is_ratio"],
        "dd_full_pct": metrics.max_drawdown_pct,
        "gate_passed": gate.passed,
        "gate_failures": [g.value for g in gate.failures],
        "fees_usd": ev.costs.fees_usd,
        "slippage_usd": ev.costs.slippage_usd,
        "funding_usd": ev.costs.funding_usd,
        "by_regime": by_regime,
    }


def run_carry_per_regime(params: dict, symbol: str, bars: list[Bar],
                         gate_cfg: GateConfig) -> list[dict]:
    """funding_carry avec le sens RE-RESOLU par regime (signe du funding du
    regime) — meme experience que T7, meme question : le « collecteur »
    combat-il la tendance ?"""
    out = []
    orig = fc.load_funding_rate
    for name, a, b in t7.REGIMES:
        lo, hi = t7._date_ms(a), t7._date_ms(b) + t7.DAY_MS - 1
        seg = [x for x in bars if lo <= x.ts <= hi]
        if len(seg) < 200:
            continue
        bps = t7.regime_funding_bps(name, symbol)

        def stub(sym: str, *args, _bps=bps, **kwargs) -> FundingRate:
            now = time.time()
            return FundingRate(symbol=(sym or symbol), avg_bps_per_8h=_bps,
                               sample_count=9999,
                               last_funding_time_ms=int(now * 1000),
                               cached_at=now)
        fc.load_funding_rate = stub
        try:
            r = run_eval("funding_carry", "REF@regime", params, symbol, seg,
                         gate_cfg)
        finally:
            fc.load_funding_rate = orig
        side = "short" if bps > 0 else ("long" if bps < 0 else "none")
        st = r["by_regime"][name]
        st["resolved_side"] = side
        st["funding_usd_regime"] = r["funding_usd"]
        out.append({"regime": name, "symbol": symbol, "side": side, **st})
    return out


# ------------------------------------------------------- comparaison avec T7

def load_t7_medians() -> dict[tuple[str, str], float]:
    """ROI/an 1x MEDIAN (3 majors) par (strategie, regime) sur les REF 1h de
    T7 — la colonne de comparaison inter-granularite."""
    if not T7_RAW.exists():
        return {}
    payload = json.loads(T7_RAW.read_text(encoding="utf-8"))
    per: dict[tuple[str, str], list[float]] = {}
    for r in payload.get("results", []):
        if r.get("config") != "REF" or ARTEFACT_STRATS.get(r["strategy"]):
            continue
        for reg, st in r.get("by_regime", {}).items():
            per.setdefault((r["strategy"], reg), []).append(st["roi_ann_pct"])
    return {k: statistics.median(v) for k, v in per.items()}


# -------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="ecrit le rapport md")
    ap.add_argument("--symbol", default=None,
                    help="filtre un symbole (ex. BTCUSDT)")
    ap.add_argument("--strategy", default=None,
                    help="filtre une strategie (ex. mean_reversion)")
    args = ap.parse_args()

    symbols = [args.symbol.upper()] if args.symbol else SYMBOLS
    strats = ([args.strategy] if args.strategy else sorted(CONFIGS))
    for s in strats:
        if s not in CONFIGS:
            print(f"strategie inconnue : {s} (valables : {sorted(CONFIGS)})")
            return 2

    t7.install_funding_stub()

    con = init_db(KLINES_DB)
    try:
        bars_by_sym = {}
        for sym in symbols:
            bars = load_bars(con, sym, INTERVAL)
            bars_by_sym[sym] = bars
            disc = sum(1 for b in bars
                       if b.ts >= t7._date_ms(DISCOVERY_START))
            print(f"# {sym} {INTERVAL}: {len(bars)} barres "
                  f"{datetime.fromtimestamp(bars[0].ts/1000, tz=timezone.utc):%Y-%m-%d}"
                  f" -> {datetime.fromtimestamp(bars[-1].ts/1000, tz=timezone.utc):%Y-%m-%d}"
                  f" | decouverte(>={DISCOVERY_START}): {disc} barres",
                  flush=True)
    finally:
        con.close()

    gate_cfg = GateConfig(random_bench_trials=50)  # bench degrade : budget etude

    results = []
    t0 = time.time()
    total = sum(len(CONFIGS[s]) for s in strats) * len(symbols)
    done = 0
    for strat in strats:
        for cfg_name, params in CONFIGS[strat].items():
            for sym in symbols:
                done += 1
                try:
                    r = run_eval(strat, cfg_name, params, sym,
                                 bars_by_sym[sym], gate_cfg)
                except Exception as exc:  # une lane qui plante ne tue pas l'etude
                    print(f"[{done}/{total}] ERREUR {strat}/{cfg_name}/{sym}: "
                          f"{type(exc).__name__}: {exc}", flush=True)
                    continue
                results.append(r)
                print(f"[{done}/{total}] {strat}/{cfg_name}/{sym} "
                      f"trades={r['closed_trades']} sh_oos={r['sharpe_oos']:.2f} "
                      f"({time.time()-t0:.0f}s)", flush=True)

    carry_rr = []
    if "funding_carry" in strats:
        for sym in symbols:
            carry_rr.extend(run_carry_per_regime(
                CONFIGS["funding_carry"]["REF"], sym, bars_by_sym[sym],
                gate_cfg))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "interval": INTERVAL,
        "regimes": t7.REGIMES,
        "discovery_start": DISCOVERY_START,
        "harness_fix": "b825da9 (stops+frais dans bar_ret — equite honnete)",
        "funding_model": {"by_regime": dict(t7.REGIME_FUNDING_BPS_8H),
                          "const_by_symbol": t7.SYM_FUNDING_CONST_BPS_8H},
        "bars_by_symbol": {s: len(b) for s, b in bars_by_sym.items()},
        "results": results,
        "carry_per_regime": carry_rr,
    }
    RAW.write_text(json.dumps(payload), encoding="utf-8")
    print(f"JSON brut : {RAW} ({time.time()-t0:.0f}s total)")

    if args.write:
        write_report(payload)
        print(f"Rapport : {REPORT}")
    return 0


# ------------------------------------------------------------------ rapport

def _fmt(v, nd=1, suf=""):
    if v is None:
        return "n/a"
    return f"{v:.{nd}f}{suf}"


def write_report(payload: dict) -> None:
    results = payload["results"]
    carry_rr = payload.get("carry_per_regime", [])
    reg_names = [r[0] for r in payload["regimes"]]
    t7_med = load_t7_medians()
    bars_n = payload.get("bars_by_symbol", {})
    lines = []
    A = lines.append
    A("# ÉTUDE T16 — la table régime × stratégie sur les 15m PROFONDES (BTC/ETH/SOL)")
    A("")
    A(f"Généré : {payload['generated_at']} — script : `scripts/studies/aster_15m_regimes.py`")
    A("")
    A("## Setup")
    A("")
    A("- Données : `data/warehouse/klines.db` (mode=ro), backfill T6 15m — "
      + " / ".join(f"{s[:-4]} {n:,}" for s, n in sorted(bars_n.items()))
      + " barres 15m, 2021-09 → 2026-09 (0 trou, T6).")
    A("- Harness : les stratégies SONT celles de la campagne (`backend/services/backtest_v2/strategies/`), signal barre i → exécution à l'OPEN i+1. **Le fix du harnais est actif** (commit b825da9 : pertes de stop + frais 4 bps/fill bookés dans `bar_ret`, mark-to-market du dernier prix) — l'équité du validateur (sharpe IS/OOS walk-forward, DD, gates) est HONNÊTE. Les stats de CE rapport restent sur le FLUX DE TRADES (couche identique à T7), comparabilité 1h/15m manche pour manche.")
    A("- **Configs = EXACTEMENT celles de T7** (REF = meilleure lane nightly du 30/09 ; V1-V3 = variations des PARAM_SPACE ; breakout = corner donchian 20). La nightly du 30/09 : 0/52 826 survivants → même convention que T7 (meilleure lane, pas survivante). Params EN BARRES → constantes de temps 4x plus courtes à 15m (EMA 20/100/200 = 5h/25h/50h ; carry hold 168 barres = 42h au lieu de 7 j). C'EST le test intraday : même logique, tape 4x plus rapide. Cas limite : `funding_carry V1_hold672` = 672×15m = 7 j = l'équivalent TEMPS du REF 1h.")
    A(f"- **Split temporel doctrinal** : fenêtre de découverte = {DISCOVERY_START} → (3 000 dernières 1h de la nightly ; couvre les 3 000 dernières 15m = 31 j). Tout le deep 2021-09 → 2026-05 est un OOS strict. Caveat T7 inchangé : les configs 1h ont « vu » les prix 2026-06 → 09 via la discovery, le régime connu n'est donc OOS qu'à la granularité, pas au tuning.")
    A("- **Funding = MODÈLE documenté de T7** (constant par régime, bps/8h ; période connue = moyennes RÉELLES Aster). funding_fade = série injectée (INDICATIF) ; funding_carry = stub par régime.")
    A("- MAE/lev_cap : reconstruction par raison de sortie, `lev_cap = 100/(maxMAE+0,5)` plafonné 12x — plafond 0-liq, jamais composé dans les ROI (tout à 1x notionnel).")
    A("- Bench random dégradé (50 tirages) : n'affecte pas les gates trades/sharpe/DD.")
    A("")
    A("Régimes (identiques T7) : " + " | ".join(f"**{n}** {a}→{b}" for n, a, b in payload["regimes"]))
    A("")
    A("## TABLE 1 — régime × stratégie à 15m (config REF, médiane des 3 majors)")
    A("")
    A("Cellule = `trades | WR | ROI/an 1x | DD | mois−` — flux de trades (frais 8 bps A/R inclus), médiane BTC/ETH/SOL.")
    A("")
    hdr = "| stratégie | " + " | ".join(reg_names) + " |"
    A(hdr)
    A("|" + "---|" * (len(reg_names) + 1))
    for strat in sorted(CONFIGS):
        if ARTEFACT_STRATS.get(strat):
            A(f"| **{strat}** (ARTEFACT — voir limites) | " + " | ".join(["—"] * len(reg_names)) + " |")
            continue
        cells = []
        for reg in reg_names:
            per = [r["by_regime"][reg] for r in results
                   if r["strategy"] == strat and r["config"] == "REF"]
            tr = statistics.median([x["trades"] for x in per])
            wrs = [x["win_rate"] for x in per if x["win_rate"] is not None]
            wr = statistics.median(wrs) * 100 if wrs else None
            rois = statistics.median([x["roi_ann_pct"] for x in per])
            dd = max(x["dd_pct"] for x in per)
            neg = max(x["months_neg"] for x in per)
            cells.append(f"{tr:.0f}t · {_fmt(wr,0,'%')} · {_fmt(rois,0,'%')} · DD{_fmt(dd,0)} · {neg}m−")
        A(f"| **{strat}** | " + " | ".join(cells) + " |")
    A("")
    A("## TABLE 2 — robustesse aux variations (configs × 3 majors = 12 lanes à 15m)")
    A("")
    A("Cellule = lanes à ROI/an > 0 / 12 (et ROI/an médian). Un edge RÉGIME-INDÉPENDANT reste > 0 partout, y compris bear 2022.")
    A("")
    A(hdr)
    A("|" + "---|" * (len(reg_names) + 1))
    for strat in sorted(CONFIGS):
        if ARTEFACT_STRATS.get(strat):
            A(f"| **{strat}** | ARTEFACT — non évaluable hors carnet réel | | | | | |")
            continue
        cells = []
        for reg in reg_names:
            lanes = [r["by_regime"][reg]["roi_ann_pct"] for r in results
                     if r["strategy"] == strat]
            pos = sum(1 for v in lanes if v > 0)
            med = statistics.median(lanes)
            cells.append(f"{pos}/12 ({_fmt(med,0,'%')})")
        A(f"| **{strat}** | " + " | ".join(cells) + " |")
    A("")
    A("## TABLE 3 — plafond de levier 0-liq par régime à 15m (config REF, min des 3 majors)")
    A("")
    A("`lev_cap = 100/(maxMAE+0,5)`, pire MAE par trade DANS le régime. En dessous : 0 liquidation par construction.")
    A("")
    A(hdr)
    A("|" + "---|" * (len(reg_names) + 1))
    for strat in sorted(CONFIGS):
        if ARTEFACT_STRATS.get(strat):
            A(f"| **{strat}** | " + " | ".join(["—"] * len(reg_names)) + " |")
            continue
        cells = []
        for reg in reg_names:
            caps = [r["by_regime"][reg]["lev_cap"] for r in results
                    if r["strategy"] == strat and r["config"] == "REF"]
            cells.append(f"{min(caps):.0f}x")
        A(f"| **{strat}** | " + " | ".join(cells) + " |")
    A("")
    A("## TABLE 4 — verdict du harnais sur la série 15m complète (config REF) — équité HONNÊTE post-fix")
    A("")
    A("Walk-forward 5 folds (IS 70 % / OOS 30 % temporels) sur ~178k barres. **Contrairement à T7, l'équité est corrigée (b825da9) : sharpe IS/OOS et DD série sont maintenant lisibles** (ils incluent stops + frais).")
    A("")
    A("| stratégie | symbole | trades | sharpe IS | sharpe OOS | ratio OOS/IS | DD série | gates |")
    A("|---|---|---|---|---|---|---|---|")
    for strat in sorted(CONFIGS):
        for r in results:
            if r["strategy"] != strat or r["config"] != "REF":
                continue
            if ARTEFACT_STRATS.get(strat):
                flag = "ARTEFACT (" + ", ".join(r["gate_failures"][:2]) + ")"
            else:
                flag = "PASS" if r["gate_passed"] else ",".join(r["gate_failures"][:3])
            A(f"| {strat} | {r['symbol'][:-4]} | {r['closed_trades']} | "
              f"{_fmt(r['sharpe_is'],2)} | {_fmt(r['sharpe_oos'],2)} | "
              f"{_fmt(r['oos_is_ratio'],2)} | {_fmt(r['dd_full_pct'],0,'%')} | {flag} |")
    A("")
    A("## TABLE 5 — comparaison inter-granularité 1h (T7) vs 15m (T16), config REF")
    A("")
    A("ROI/an 1x médian des 3 majors par régime. `1h→15m` = même config, constantes de temps /4. Cohérence 1h/15m = signe de robustesse ; divergence = edge dépendant de l'horizon.")
    A("")
    A("| stratégie | " + " | ".join(reg_names) + " |")
    A("|" + "---|" * (len(reg_names) + 1))
    for strat in sorted(CONFIGS):
        if ARTEFACT_STRATS.get(strat):
            A(f"| **{strat}** | " + " | ".join(["—"] * len(reg_names)) + " |")
            continue
        cells = []
        for reg in reg_names:
            new = [r["by_regime"][reg]["roi_ann_pct"] for r in results
                   if r["strategy"] == strat and r["config"] == "REF"]
            med15 = statistics.median(new)
            old = t7_med.get((strat, reg))
            if old is None:
                cells.append(f"15m {_fmt(med15,0,'%')}")
            else:
                cells.append(f"{_fmt(old,0,'%')} → {_fmt(med15,0,'%')}")
        A(f"| **{strat}** | " + " | ".join(cells) + " |")
    A("")
    A("## Détail par stratégie — config REF, moyenne des 3 majors")
    A("")
    for strat in sorted(CONFIGS):
        A(f"### {strat}")
        if ARTEFACT_STRATS.get(strat) == "microstructure":
            A("")
            A("**ARTEFACT MICROSTRUCTURE — non évaluable hors carnet réel.** "
              "Le modèle encaisse une fraction de la range de CHAQUE barre "
              "(178k × 4 « trades ») sans modèle d'adverse selection : composé "
              "sur 178k barres ça donne des ROI de 10^15 % et plus, "
              "physiquement absurdes (T7 l'avait déjà rejeté sur 1h). Re-doit "
              "passer par un carnet réel (1m + profondeur) avant tout verdict.")
            A("")
            continue
        if ARTEFACT_STRATS.get(strat) == "serie synthetique":
            A("")
            A("**INDICATIF — série de funding synthétique.** Le fade est piloté "
              "par l'enveloppe déterministe injectée (aucun historique de "
              "funding avant 2025) : fondre un oscillateur mean-revert par "
              "construction gagne par construction. À rejouer sur "
              "`funding_history` réelle (2025-10 →) uniquement.")
            A("")
        A("| régime | trades/sym | WR | ROI/an 1x | DD max | maxMAE | lev_cap | mois− | pire mois | record mois |")
        A("|---|---|---|---|---|---|---|---|---|---|")
        for reg in reg_names:
            per = [r["by_regime"][reg] for r in results
                   if r["strategy"] == strat and r["config"] == "REF"]
            wrs = [x["win_rate"] for x in per if x["win_rate"] is not None]
            row = [
                f"{statistics.mean([x['trades'] for x in per]):.0f}",
                _fmt(statistics.mean(wrs) * 100 if wrs else None, 0, "%"),
                _fmt(statistics.mean([x["roi_ann_pct"] for x in per]), 0, "%"),
                _fmt(max(x["dd_pct"] for x in per), 0),
                _fmt(max(x["max_mae_pct"] for x in per), 0, "%"),
                f"{min(x['lev_cap'] for x in per):.0f}x",
                f"{max(x['months_neg'] for x in per)}",
                _fmt(min(x["month_worst_pct"] for x in per), 1, "%"),
                _fmt(max(x["month_best_pct"] for x in per), 1, "%"),
            ]
            A(f"| {reg} | " + " | ".join(row) + " |")
        if strat == "funding_carry" and carry_rr:
            A("")
            A("**Re-résolution du sens PAR régime** (signe du funding du régime) :")
            A("")
            A("| régime | sens résolu | trades/sym | WR | ROI/an 1x | DD |")
            A("|---|---|---|---|---|---|")
            for reg in reg_names:
                per = [x for x in carry_rr if x["regime"] == reg]
                if not per:
                    continue
                wrs = [x["win_rate"] for x in per if x["win_rate"] is not None]
                A(f"| {reg} | {per[0]['side']} | "
                  f"{statistics.mean([x['trades'] for x in per]):.0f} | "
                  f"{_fmt(statistics.mean(wrs)*100 if wrs else None,0,'%')} | "
                  f"{_fmt(statistics.mean([x['roi_ann_pct'] for x in per]),0,'%')} | "
                  f"{_fmt(max(x['dd_pct'] for x in per),0)} |")
        A("")
    A("## Verdict (mission T16)")
    A("")
    A("**1. Réponse à la question : à la granularité intraday, AUCUN edge "
      "positif RÉGIME-INDÉPENDANT n'apparaît — et les rares positifs 1h ne "
      "survivent pas au passage 15m.** La table de comparaison (TABLE 5) est "
      "sans appel :")
    A("")
    A("- **momentum** — l'edge de cycle 2023-2024 de T7 (+55 à +61 %/an en "
      "recovery/bull24/chop à 1h) **S'EFFONDRE à 15m** (+7 % recovery, −42 % "
      "bull24, −14 % chop ; 0/12 dans le connu, −28 %/an médian). La même "
      "logique 4x plus rapide multiplie les trades par 3-4 (SOL 1 221 → 2 811) "
      "donc les frais cumulés (~4,5 pts/5 ans) et le whipsaw. Ce n'était PAS "
      "un edge du marché, c'était un edge d'HORIZON (1h) — et il est mort "
      "avant même 2025. La cohérence inter-granularité n'existe pas pour lui.")
    A("- **mean_reversion** — l'invariance vraie se REPRODUIT à 15m : WR "
      "43-59 % dans tous les régimes (identique au 38-52 % de T7), PnL "
      "négatif partout (0/12 bear, 0/12 connu, −40 %/an médian au connu). Le "
      "WR invariant est une propriété STRUCTURELLE des majors (inter-régimes "
      "ET inter-granularité) ; le RR inversé + frais la tuent aux deux "
      "horizons. 812 trades/sym au connu = churn payé pour rien.")
    A("- **breakout** — la seule émergence 15m : positif en recovery 2023 "
      "(+13 %, 8/12 — EXACTEMENT le chiffre 1h) ET désormais bull24 (+31 %, "
      "3/12) et chop (+12 %, 4/12) où 1h était négatif. Donchian 20 à 15m = "
      "cassure 5 h. Mais **mort dans le connu (−21 %, 1/12)** et bear (−52 %) "
      "— un pattern de régime 2023-2024, pas un edge transportable.")
    A("- **funding_carry** — même structure qu'à 1h : le seul positif est "
      "bear 2022 (+23 %/an, 8/12, l'accident du short passif) ; partout "
      "ailleurs −26 à −94 %. Re-résolution du sens par régime : −25 à −98 % "
      "partout : le « collecteur » combat toujours la tendance.")
    A("- **funding_fade / volatility_harvesting** — artefacts (série "
      "synthétique / microstructure), non jugables ; leurs sharpe OOS "
      "« élevés » (vol_harvest 8-12) sont la signature de l'artefact, pas "
      "d'un edge.")
    A("")
    A("**2. Le harnais honnête confirme (post-fix b825da9) : 0 lane PASS sur "
      "les gates, sharpe OOS ≤ 0,04 partout hors artefacts, DD série "
      "72-100 %.** Contrairement à T7 (équité biaisée), ces chiffres sont "
      "lisibles : à 15m, avec les stops et les frais comptés, les 6 familles "
      "campagne sont MORTES sur le deep. Cohérent avec la nightly 0/52 826.")
    A("")
    A("**3. La réponse au portrait général : 1h = momentum de cycle + "
      "invariance MR du WR ; 15m = RIEN de plus.** La granularité intraday ne "
      "révèle pas d'edges cachés sur OHLCV majors : elle paie 2-4x plus de "
      "frais pour le même signal. Le seul résultat transversal robuste "
      "(recovery 2023 positif pour momentum/breakout aux deux horizons) "
      "concerne un régime terminé, et le connu 2025-2026 est négatif pour "
      "TOUT (4/4 familles, les deux granularités).")
    A("")
    A("**4. Implication forward intraday (la question T16) : les signaux 15m "
      "du tape n'ont AUCUNE base dans ces 6 familles.** Si le forward "
      "intraday doit exister, sa base est AILLEURS : microstructure réelle "
      "(carnet 1m + profondeur, phase 2 — vol_harvest y est rejugable), "
      "ordre-flow/tape (CVD, absorptions), données fomo — pas des stratégies "
      "OHLCV re-descendues en granularité. Pour le stack : aucune lane 15m "
      "candidate ; le test wallet séquentiel est inutile (morts avant). Au "
      "registre (docs/20) : mean_reversion CONFIRMÉ CONTEXTE (WR invariant "
      "inter-granularité — l'unique piste survivante reste RR non inversé + "
      "maker) ; momentum CONTEXTE confirmé mais l'edge était 1h-only ; "
      "breakout 15m CONTEXTE (pattern recovery/bull24, mort au connu) ; "
      "funding_carry NUL confirmé ; les 2 artefacts NUL hors phase 2.")
    A("")
    A("## Limites honnêtes")
    A("")
    A("1. **Funding modélisé** sur 2021-2024 (hypothèse par régime, T7) ; la jambe funding des directionnels reste hors trade_returns (±0,4 bps/8h ≈ négligeable). Verdicts RELATIFS priment.")
    A("2. **Fills modèle** : stops au prix du stop (optimiste sur les gaps — LUNA/FTX, et les 15m gapent 4x moins que les 1h) ; takes comme limites.")
    A("3. **Params en barres** : la comparaison 1h→15m confond « même logique, horizon /4 ». Elle teste la logique, pas les lanes machine exactes (cascade/survivor/vol_spike : horizons plus fins).")
    A("4. **Attribution des trades** par régime d'ENTRÉE ; composition séquentielle = positions non chevauchantes.")
    A("5. **ASTER hors scope deep** (1 an de données, jugé par la campagne nocturne).")
    A("6. Bench random dégradé (50 tirages) : n'affecte pas les gates trades/sharpe/DD.")
    A("7. ROI composés sur trades 1x : SOL domine les moyennes en 2021-2023 — lire les MÉDIANES des 3 majors (TABLE 1/5), pas les moyennes (détail).")
    A("")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
