#!/usr/bin/env python3
"""ETUDE (one-shot, mission T7) : les 6 strategies CAMPAGNE sur l'historique
profond 2021-09 -> 2026-09 (backfill T6) — quels edges survivent aux regimes ?

Question (mission T7) : la campagne a ete validee sur ~1 an de donnees et la
fenetre de decouverte de la derniere campagne = 3 000 barres 1h (2026-06 ->
2026-09). Les configs re-testees ici n'ONT JAMAIS VU 2021->2026-05 : tout le
deep est un OOS temporel strict (split par le TEMPS, pas aleatoire).

Harness : les strategies SONT celles de la campagne (backend/services/
backtest_v2/strategies/*) — signal barre i -> execution a l'OPEN de i+1
(garantie anti-look-ahead du module). On ne re-implemente rien.

Configs : les "seuils reels" = meilleure lane par strategie de la DERNIERE
campagne nightly (store backtest.db, majors 1h) + 2-3 variations prises dans
les propres PARAM_SPACE des modules. Cas particulier breakout : toutes les
lanes de la derniere campagne ont fait 0 trades sur la fenetre recente
(donchian 100 + confirmation 2 : rien de confirme en 2026) -> corner le plus
actif de la MEME grille campagne (donchian 20, confirm 1).

Funding (MODELE DOCUMENTE, pas une mesure) : le cache Aster n'existe que pour
2025+ ; sur le deep on applique un funding 8h CONSTANT PAR REGIME (hypothese
autorisee par la mission) ; pour la periode connue la moyenne REELLE mesuree
(data/warehouse/klines.db::funding_history) :
    bull 2021-H2 +2.0 bps/8h | bear 2022 -0.5 | recovery 2023 +0.5
    bull 2024-H1 +1.5 | chop 2024-H2 +0.5 | connu 2025-26 : reel (BTC +0.34,
    ETH +0.37, SOL -0.01).
- funding_fade recoit une serie INJECTEE (base regime + oscillation
  deterministe du module) -> INDICATIF : fondre un oscillateur deterministe
  mean-revert par construction est un edge DE CONSTRUCTION.
- funding_carry resout son sens UNE fois depuis la moyenne -> sous funding
  constant il devient un short permanent : degenerescence documentee, on
  ajoute une re-resolution du sens PAR REGIME (signe du funding du regime).
- Les 4 strategies directionnelles recoivent une constante par symbole
  (moyenne du modele regime : BTC 0.44 / ETH 0.45 / SOL 0.41 bps/8h) via un
  stub de load_funding_rate.
AUCUNE ecriture hors reports/ ; DB lues en mode=ro.

Rendements : le moteur exprime tout a 1x notionnel (le levier ne sert qu'au
check de liquidation). MAE reconstruit par raison de sortie (stop -> barre du
stop ; sinon -> prochaine entree) pour la regle 0-liq de la doctrine :
    lev_cap = 100 / (maxMAE_regime + 0.5)   (plafond, pas une recommandation)
et on ne compose JAMAIS le levier dans les ROI affiches.

Sortie : reports/aster_deep_regimes.md (--write) + JSON brut.

Stdlib pure. Usage :
    .venv/bin/python scripts/studies/aster_deep_regimes.py            # run
    .venv/bin/python scripts/studies/aster_deep_regimes.py --write    # + rapport
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
# fetch_klines importe des modules freres (aster_rate) : la racine de scripts/
# doit etre importable, comme quand la campagne est lancee en script direct.
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.fetch_klines import init_db, load_bars  # noqa: E402
from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.costs import FundingRate  # noqa: E402
from backend.services.backtest_v2.engine import (  # noqa: E402
    CampaignConfig,
    evaluate_one,
)
from backend.services.backtest_v2.gates import GateConfig  # noqa: E402
from backend.services.backtest_v2 import strategies as strat_pkg  # noqa: E402
from backend.services.backtest_v2.strategies import (  # noqa: E402
    funding_fade as ff,
    momentum as mom,
    mean_reversion as mr,
    breakout as bo,
    funding_carry as fc,
    volatility_harvesting as vh,
)

KLINES_DB = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "aster_deep_regimes.md"
RAW = ROOT / "reports" / "aster_deep_regimes_raw.json"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVAL = "1h"

# ------------------------------------------------------------------- regimes
# Decoupage classique (mission T7). Bornes UTC, inclusives.
REGIMES = [
    ("bull_2021H2", "2021-09-01", "2021-12-31"),
    ("bear_2022",   "2022-01-01", "2022-12-31"),
    ("recovery_2023", "2023-01-01", "2023-12-31"),
    ("bull_2024H1", "2024-01-01", "2024-06-30"),
    ("chop_2024H2", "2024-07-01", "2024-12-31"),
    ("connu_2025_2026", "2025-01-01", "2026-09-30"),
]

# Fenetre de DECOUVERTE de la derniere campagne (3000 dernieres 1h).
DISCOVERY_START = "2026-06-06"

# Funding MODELE par regime (bps/8h) ; dict = moyenne REELLE mesuree Aster.
REGIME_FUNDING_BPS_8H = {
    "bull_2021H2": 2.0,
    "bear_2022": -0.5,
    "recovery_2023": 0.5,
    "bull_2024H1": 1.5,
    "chop_2024H2": 0.5,
    "connu_2025_2026": {"BTCUSDT": 0.343, "ETHUSDT": 0.367, "SOLUSDT": -0.009},
}
# Constante par symbole (moyenne du modele regime) pour les 4 strats directes.
SYM_FUNDING_CONST_BPS_8H = {"BTCUSDT": 0.44, "ETHUSDT": 0.45, "SOLUSDT": 0.41}

DAY_MS = 86_400_000


def _date_ms(s: str) -> int:
    return int(datetime.fromisoformat(s + "T00:00:00+00:00").timestamp() * 1000)


def regime_of(ts_ms: int) -> str:
    for name, a, b in REGIMES:
        if _date_ms(a) <= ts_ms <= _date_ms(b) + DAY_MS - 1:
            return name
    return "hors_regimes"


def regime_funding_bps(regime: str, symbol: str) -> float:
    v = REGIME_FUNDING_BPS_8H[regime]
    if isinstance(v, dict):
        return float(v[symbol])
    return float(v)


# ------------------------------------------------------- configs testees
# REF = meilleure lane nightly du 30/09 (majors 1h, store backtest.db).
# V* = variations prises dans les PARAM_SPACE des modules eux-memes.
CONFIGS: dict[str, dict[str, dict]] = {
    "momentum": {
        "REF": dict(fast_ema=20, slow_ema=100, regime_ema=200, allow_short=False,
                    stop_bps=200, take_bps=1000, max_leverage=2),
        "V1_short": dict(fast_ema=20, slow_ema=100, regime_ema=200, allow_short=True,
                         stop_bps=200, take_bps=1000, max_leverage=2),
        "V2_stop500": dict(fast_ema=20, slow_ema=100, regime_ema=200, allow_short=False,
                           stop_bps=500, take_bps=1000, max_leverage=2),
        "V3_regime120": dict(fast_ema=20, slow_ema=100, regime_ema=120,
                             allow_short=False, stop_bps=200, take_bps=1000,
                             max_leverage=2),
    },
    "mean_reversion": {
        "REF": dict(lookback=100, entry_z=2.5, exit_z=0.5, use_std=True,
                    allow_short=False, stop_bps=150, take_bps=200, max_leverage=3),
        "V1_short": dict(lookback=100, entry_z=2.5, exit_z=0.5, use_std=True,
                         allow_short=True, stop_bps=150, take_bps=200, max_leverage=3),
        "V2_stop300": dict(lookback=100, entry_z=2.5, exit_z=0.5, use_std=True,
                           allow_short=False, stop_bps=300, take_bps=200,
                           max_leverage=3),
        "V3_z2.0": dict(lookback=100, entry_z=2.0, exit_z=0.5, use_std=True,
                        allow_short=False, stop_bps=150, take_bps=200, max_leverage=3),
    },
    "breakout": {
        "REF": dict(donchian_len=20, breakout_mult=0.0, confirmation_bars=1,
                    use_close=True, allow_short=False, stop_bps=200, take_bps=400,
                    max_leverage=2),
        "V1_short": dict(donchian_len=20, breakout_mult=0.0, confirmation_bars=1,
                         use_close=True, allow_short=True, stop_bps=200, take_bps=400,
                         max_leverage=2),
        "V2_stop500": dict(donchian_len=20, breakout_mult=0.0, confirmation_bars=1,
                           use_close=True, allow_short=False, stop_bps=500,
                           take_bps=400, max_leverage=2),
        "V3_don100": dict(donchian_len=100, breakout_mult=0.0, confirmation_bars=1,
                          use_close=True, allow_short=False, stop_bps=200,
                          take_bps=400, max_leverage=2),
    },
    "funding_fade": {
        "REF": dict(lookback=200, entry_z=2.5, exit_z=0.5, allow_short=True,
                    stop_bps=200, max_leverage=3),
        "V1_z2.0": dict(lookback=200, entry_z=2.0, exit_z=0.5, allow_short=True,
                        stop_bps=200, max_leverage=3),
        "V2_lb100": dict(lookback=100, entry_z=2.5, exit_z=0.5, allow_short=True,
                         stop_bps=200, max_leverage=3),
        "V3_stop400": dict(lookback=200, entry_z=2.5, exit_z=0.5, allow_short=True,
                           stop_bps=400, max_leverage=3),
    },
    "funding_carry": {
        "REF": dict(side_filter=["auto"], hold_max_bars=168, allow_short=True,
                    stop_bps=200, max_leverage=2),
        "V1_hold672": dict(side_filter=["auto"], hold_max_bars=672, allow_short=True,
                           stop_bps=200, max_leverage=2),
        "V2_stop500": dict(side_filter=["auto"], hold_max_bars=168, allow_short=True,
                           stop_bps=500, max_leverage=2),
    },
    "volatility_harvesting": {
        "REF": dict(spread_bps=5, allow_short=True, max_leverage=2),
        "V1_s10": dict(spread_bps=10, allow_short=True, max_leverage=2),
        "V2_s20": dict(spread_bps=20, allow_short=True, max_leverage=2),
    },
}

STRAT_MODULES = {"momentum": mom, "mean_reversion": mr, "breakout": bo,
                 "funding_fade": ff, "funding_carry": fc,
                 "volatility_harvesting": vh}

# Strategies dont le verdict deep est INVALIDE par construction (voir rapport).
ARTEFACT_STRATS = {"volatility_harvesting": "microstructure",
                   "funding_fade": "serie synthetique"}


# ------------------------------------------------------------ funding stubs

def install_funding_stub() -> None:
    """Patche load_funding_rate DANS CHAQUE module de strategie (les modules
    bindent le nom a l'import : patcher costs.* ne suffirait pas)."""
    def stub(symbol: str, *args, **kwargs) -> FundingRate:
        sym = (symbol or "BTCUSDT").upper()
        base = SYM_FUNDING_CONST_BPS_8H.get(sym, 0.5)
        now = time.time()
        return FundingRate(
            symbol=sym, avg_bps_per_8h=base, sample_count=9999,
            last_funding_time_ms=int(now * 1000), cached_at=now,
        )
    for name, mod in STRAT_MODULES.items():
        if name == "funding_fade":
            continue  # serie injectee, pas de cache
        mod.load_funding_rate = stub


def injected_fade_series(bars: list[Bar], symbol: str) -> list[float]:
    """Serie funding INJECTEE pour funding_fade : base par regime (modele
    documente) + enveloppe deterministe du module (base=0 -> amplitude 0.5)."""
    osc = ff.synthetic_funding_series(len(bars), 0.0, symbol)
    return [regime_funding_bps(regime_of(b.ts), symbol) + osc[i]
            for i, b in enumerate(bars)]


# ---------------------------------------------------------- stats par regime

def _exit_index(k: int, entries: list[tuple[int, int]], reasons: list[str],
                bars: list[Bar], entry_price: float, side: int,
                stop_frac: float | None, take_frac: float | None) -> int:
    """Index de sortie reconstruit. stop/take : premiere barre qui touche le
    seuil (entree incluse, comme les modules). Sinon : derniere barre avant
    l'entree suivante (reverse/flat/roll/eod — sortie a l'OPEN suivant)."""
    n = len(bars)
    ei = entries[k][0]
    nxt = entries[k + 1][0] if k + 1 < len(entries) else n
    reason = reasons[k] if k < len(reasons) else ""
    hi = min(nxt, n)
    if side == 1 and stop_frac and "stop" in reason:
        for i in range(ei, hi):
            if bars[i].low <= entry_price * (1.0 - stop_frac):
                return i
    if side == -1 and stop_frac and "stop" in reason:
        for i in range(ei, hi):
            if bars[i].high >= entry_price * (1.0 + stop_frac):
                return i
    if side == 1 and take_frac and "take" in reason:
        for i in range(ei, hi):
            if bars[i].high >= entry_price * (1.0 + take_frac):
                return i
    if side == -1 and take_frac and "take" in reason:
        for i in range(ei, hi):
            if bars[i].low <= entry_price * (1.0 - take_frac):
                return i
    return max(ei, min(nxt - 1, n - 1))


def regime_stats(bars: list[Bar], bar_ret: list[float],
                 entries: list[tuple[int, int]], reasons: list[str],
                 trade_returns: list[float], stop_frac: float | None,
                 take_frac: float | None, lo_ms: int, hi_ms: int) -> dict:
    """Stats d'UNE lane dans UN regime, calculees sur le FLUX DE TRADES.

    POURQUOI PAS LA COURBE D'EQUITE DU HARNAIS (decouverte T7) : les modules
    mettent a 0 la barre de stop (la perte stoppee n'est jamais comptee dans
    bar_ret) et n'y incluent pas les frais (8 bps seulement dans les trades).
    L'equite du harnais est donc SYSTEMATIQUEMENT optimiste des qu'une lane
    stoppe ; le flux de trades (fills reels + frais + funding) est la couche
    honnete. Trades attribues au regime d'ENTREE, composes sequentiellement
    (strategies a etat : positions non chevauchantes).
    """
    n = len(bars)
    idx = [i for i, b in enumerate(bars) if lo_ms <= b.ts <= hi_ms]
    if not idx:
        return None
    lo_i, hi_i = idx[0], idx[-1]
    years = (bars[hi_i].ts - bars[lo_i].ts) / (365.25 * DAY_MS)

    eq = 1.0
    peak = 1.0
    dd = 0.0
    trades = 0
    wins = 0
    max_mae = 0.0
    months: dict[str, float] = {}
    for k, (ei, side) in enumerate(entries):
        if not (lo_i <= ei <= hi_i):
            continue
        net = trade_returns[k] if k < len(trade_returns) else 0.0
        trades += 1
        if net > 0:
            wins += 1
        eq *= (1.0 + net)
        peak = max(peak, eq)
        if peak > 0:
            dd = max(dd, (peak - eq) / peak * 100.0)
        m = datetime.fromtimestamp(bars[ei].ts / 1000, tz=timezone.utc).strftime("%Y-%m")
        months[m] = months.get(m, 0.0) * (1.0 + net) + net
        ex = _exit_index(k, entries, reasons, bars, bars[ei].open, side,
                         stop_frac, take_frac)
        if side in (1, -1) and ex >= ei:
            seg = bars[ei:ex + 1]
            if side == 1:
                worst = min(s.low for s in seg)
                mae = (bars[ei].open - worst) / bars[ei].open * 100.0
            else:
                worst = max(s.high for s in seg)
                mae = (worst - bars[ei].open) / bars[ei].open * 100.0
            max_mae = max(max_mae, max(0.0, mae))

    mvals = [(m, v * 100.0) for m, v in months.items()]
    lev_cap = 100.0 / (max_mae + 0.5) if max_mae > 0 else 12.0
    return {
        "regime_months": len(mvals),
        "trades": trades,
        "win_rate": (wins / trades) if trades else None,
        "roi_pct": (eq - 1.0) * 100.0,
        "roi_ann_pct": ((eq - 1.0) * 100.0 / years) if years > 0 else 0.0,
        "dd_pct": dd,
        "max_mae_pct": max_mae,
        "lev_cap": min(lev_cap, 12.0),  # doctrine : plafond majos 12x
        "months_neg": sum(1 for _, v in mvals if v < 0),
        "month_worst_pct": min((v for _, v in mvals), default=0.0),
        "month_best_pct": max((v for _, v in mvals), default=0.0),
    }


def empty_regime_stats() -> dict:
    return {"regime_months": 0, "trades": 0, "win_rate": None, "roi_pct": 0.0,
            "roi_ann_pct": 0.0, "dd_pct": 0.0, "max_mae_pct": 0.0,
            "lev_cap": 12.0, "months_neg": 0, "month_worst_pct": 0.0,
            "month_best_pct": 0.0}


# ------------------------------------------------------------------- moteur

def _fracs(params: dict) -> tuple[float | None, float | None]:
    stop = float(params["stop_bps"]) / 10_000.0 if "stop_bps" in params else None
    take = float(params["take_bps"]) / 10_000.0 if "take_bps" in params else None
    return stop, take


def run_eval(strat: str, cfg_name: str, params: dict, symbol: str,
             bars: list[Bar], gate_cfg: GateConfig) -> dict:
    p = dict(params)
    p["symbol"] = symbol
    if strat == "funding_fade":
        p["funding_bps_series"] = injected_fade_series(bars, symbol)
    evaluate = strat_pkg.REGISTRY[strat][0]
    ev = evaluate(p, bars)
    identity = strat_pkg.make_identity(strat, p, symbol=symbol, interval=INTERVAL)
    cfg = CampaignConfig(run_id=f"study-{strat}-{symbol}-{cfg_name}",
                         data_snapshot_id="deep-2021-2026-backfill-T6",
                         gate_config=gate_cfg)
    metrics, gate, _bench, extra = evaluate_one(identity, ev, bars, cfg)
    entries = ev.blob.get("entries") or []
    reasons = ev.blob.get("exit_reasons") or []
    if strat == "volatility_harvesting":
        entries = [(i, 1) for i in (ev.blob.get("harvest_bars") or [])]
        reasons = ["take"] * len(entries)
    stop_frac, take_frac = _fracs(params)
    by_regime = {}
    for name, a, b in REGIMES:
        st = regime_stats(bars, list(ev.bar_returns_per_bar), entries, reasons,
                          list(ev.trade_returns), stop_frac, take_frac,
                          _date_ms(a), _date_ms(b) + DAY_MS - 1)
        by_regime[name] = st or empty_regime_stats()
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
    """Experience supplementaire : funding_carry avec le sens re-resolu par
    regime (signe du funding du regime). Revele la structure du edge : le sens
    collecteur combat-il la tendance ?"""
    out = []
    orig = fc.load_funding_rate
    for name, a, b in REGIMES:
        lo, hi = _date_ms(a), _date_ms(b) + DAY_MS - 1
        seg = [x for x in bars if lo <= x.ts <= hi]
        if len(seg) < 200:
            continue
        bps = regime_funding_bps(name, symbol)

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="ecrit le rapport md")
    args = ap.parse_args()

    install_funding_stub()

    con = init_db(KLINES_DB)
    try:
        bars_by_sym = {}
        for sym in SYMBOLS:
            bars = load_bars(con, sym, INTERVAL)
            bars_by_sym[sym] = bars
            print(f"# {sym} {INTERVAL}: {len(bars)} barres "
                  f"{datetime.fromtimestamp(bars[0].ts/1000, tz=timezone.utc):%Y-%m-%d}"
                  f" -> {datetime.fromtimestamp(bars[-1].ts/1000, tz=timezone.utc):%Y-%m-%d}",
                  flush=True)
    finally:
        con.close()

    gate_cfg = GateConfig(random_bench_trials=50)  # bench degrade : budget etude

    results = []
    t0 = time.time()
    total = sum(len(c) for c in CONFIGS.values()) * len(SYMBOLS)
    done = 0
    for strat in sorted(CONFIGS):
        for cfg_name, params in CONFIGS[strat].items():
            for sym in SYMBOLS:
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

    # carry re-resolu par regime (config REF uniquement)
    carry_rr = []
    for sym in SYMBOLS:
        carry_rr.extend(run_carry_per_regime(CONFIGS["funding_carry"]["REF"],
                                             sym, bars_by_sym[sym], gate_cfg))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regimes": REGIMES,
        "discovery_start": DISCOVERY_START,
        "funding_model": {"by_regime": dict(REGIME_FUNDING_BPS_8H),
                          "const_by_symbol": SYM_FUNDING_CONST_BPS_8H},
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
    lines = []
    A = lines.append
    A("# ÉTUDE T7 — les 6 stratégies CAMPAGNE sur le deep 2021→2026 (BTC/ETH/SOL 1h)")
    A("")
    A(f"Généré : {payload['generated_at']} — script : `scripts/studies/aster_deep_regimes.py`")
    A("")
    A("## Setup")
    A("")
    A("- Données : `data/warehouse/klines.db` (mode=ro), backfill T6 — BTC 44 524 / ETH 44 383 / SOL 44 335 barres 1h, 2021-09 → 2026-09.")
    A("- Harness : les stratégies SONT celles de la campagne (`backend/services/backtest_v2/strategies/`), signal barre i → exécution à l'OPEN i+1. Aucune ré-implémentation, DB en mode=ro.")
    A("- **Split temporel doctrinal** : configs issues de la DERNIÈRE campagne nightly (30/09, fenêtre de découverte = 3 000 dernières 1h ≈ 2026-06-06 →). Tout le deep 2021 → 2026-05 est un OOS strict, jamais vu par ces seuils.")
    A("- Configs : REF = meilleure lane nightly par stratégie (majors 1h, store `backtest.db`) ; V1-V3 = variations dans les PARAM_SPACE des modules. Breakout : toutes les lanes nightly = 0 trades (donchian 100 + confirm 2 ne déclenche pas en 2026) → corner le plus actif de la même grille.")
    A("- **Funding = MODÈLE documenté** (pas une mesure) : constant par régime (bull 2021-H2 +2,0 bps/8h ; bear 2022 −0,5 ; recovery 2023 +0,5 ; bull 2024-H1 +1,5 ; chop 2024-H2 +0,5) ; période connue = moyennes RÉELLES Aster (BTC +0,34 / ETH +0,37 / SOL −0,01).")
    A("- **MAE/lev_cap** : MAE reconstruit par raison de sortie (stop → barre du stop, sinon → prochaine entrée) ; `lev_cap = 100/(maxMAE+0,5)` plafonné 12x (règle 0-liq) — plafond, jamais composé dans les ROI (tout est affiché à 1x notionnel).")
    A("- **DÉCOUVERTE MAJEURE (le harnais lui-même)** : les courbes d'équité des 6 modules mettent à 0 la barre de stop (la perte stoppée n'est JAMAIS comptée dans `bar_ret`) et n'y incluent pas les frais (8 bps seulement dans les trades). Preuve : funding_carry BTC bear 2022 — équité +237 % alors que la somme des trades vaut −124 %. Toute stat d'équité du validateur (sharpe IS/OOS walk-forward, DD, gates) est donc OPTIMISTE dès qu'une lane stoppe. **Toutes les stats de CE rapport (ROI/DD/mois) sont calculées sur le FLUX DE TRADES** (fills réels, frais inclus), la couche honnête.")
    A("- Bench random dégradé (50 tirages) pour le budget étude ; gates principaux (trades/sharpe/DD/ratio) inchangés.")
    A("")
    A("Régimes : " + " | ".join(f"**{n}** {a}→{b}" for n, a, b in payload["regimes"]))
    A("")
    A("## TABLE 1 — régime × stratégie (config REF, médiane des 3 majors)")
    A("")
    A("Cellule = `trades | WR | ROI/an 1x | DD | mois−` — flux de trades, médiane BTC/ETH/SOL. ROI à 1x : le levier 0-liq autorisé est en TABLE 3.")
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
    A("## TABLE 2 — robustesse aux variations (configs × 3 majors = 12 lanes)")
    A("")
    A("Cellule = lanes à ROI/an > 0 / 12 (et ROI/an médian). Un edge RÉGIME-INDÉPENDANT reste > 0 partout, y compris bear 2022.")
    A("")
    A(hdr)
    A("|" + "---|" * (len(reg_names) + 1))
    for strat in sorted(CONFIGS):
        if ARTEFACT_STRATS.get(strat):
            A(f"| **{strat}** | ARTEFACT — non évaluable sur 1h deep | | | | | |")
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
    A("## TABLE 3 — plafond de levier 0-liq par régime (config REF, min des 3 majors)")
    A("")
    A("`lev_cap = 100/(maxMAE+0,5)`, pire MAE par trade DANS le régime. En dessous de ce levier : 0 liquidation par construction.")
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
    A("## TABLE 4 — verdict du harnais sur la série complète (config REF)")
    A("")
    A("Walk-forward 5 folds (IS 70 % / OOS 30 % temporels) sur les 44k barres + gates campagne. **ATTENTION : sharpe IS/OOS et DD série = courbe d'équité du harnais = biaisée (stops non comptés, frais absents — voir découverte en Setup).** Ils valident la COHÉRENCE IS/OOS, pas le niveau. `param_instability` = sensibilité non mesurée (budget).")
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
              f"{r['sharpe_is']:.2f} | {r['sharpe_oos']:.2f} | "
              f"{r['oos_is_ratio']:.2f} | {r['dd_full_pct']:.0f}% | {flag} |")
    A("")
    A("## Détail par stratégie — config REF, moyenne des 3 majors")
    A("")
    for strat in sorted(CONFIGS):
        A(f"### {strat}")
        if ARTEFACT_STRATS.get(strat) == "microstructure":
            A("")
            A("**ARTEFACT MICROSTRUCTURE — non évaluable sur 1h deep.** Le modèle "
              "encaisse une fraction de la range de CHAQUE barre (43 000+ « trades ») "
              "sans modèle d'adverse selection : composé sur 44k barres ça donne des "
              "ROI de 10^40 %, physiquement absurdes. Le harnais le sait déjà : la "
              "campagne rejette ses lanes (`param_instability`, `costs_incomplete`, "
              "`microstructure_validated=False`). Redoit passer par un carnet réel "
              "(phase 2, 1m/15m + profondeur) avant tout verdict.")
            A("")
            continue
        if ARTEFACT_STRATS.get(strat) == "serie synthetique":
            A("")
            A("**INDICATIF — serie de funding synthétique.** Le fade est piloté par "
              "l'enveloppe déterministe injectée (le module ne dispose d'aucun "
              "historique de funding avant 2025) : fondre un oscillateur "
              "mean-revert par construction gagne par construction. Ses 12/12 "
              "positifs de la TABLE 2 sont la signature de l'artefact, PAS d'un "
              "edge. À rejouer sur `funding_history` réelle (2025-10 →) uniquement.")
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
            A("**Re-résolution du sens PAR régime** (signe du funding du régime) — "
              "la jambe prix du « collecteur » combat la tendance :")
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
    A("## Verdict (mission T7)")
    A("")
    A("**0. Le trésor de l'étude — un bug du harnais, pas des stratégies :** "
      "l'équité des 6 modules omet les pertes de stop (barre mise à 0) et les "
      "frais. Toute la couche équité du validateur nocturne (sharpe IS/OOS, DD, "
      "gates, TABLE 4) est optimiste dès qu'une lane stoppe ; la couche honnête "
      "est le flux de trades. À corriger dans le harnais AVANT de croire un "
      "sharpe OOS de campagne. Ce verdict est RELATIF au flux de trades — il "
      "survit au fix ; les ABSOLUS d'équité de la campagne, non.")
    A("")
    A("**1. Réponse à la question : AUCUN des 6 n'est un edge positif "
      "RÉGIME-INDÉPENDANT à 1x, frais taker 8 bps A/R, sur 1h deep.** La "
      "hiérarchie (flux de trades) :")
    A("")
    A("- **momentum** — RÉGIME-DÉPENDANT, cycle 2023-2024 uniquement : positif en "
      "recovery/bull/chop (8-11/12 lanes, +49 à +61 %/an médians), négatif dans "
      "bull 2021-H2 (2/12) et MORT dans la période connue (0/12, −25 %/an médian, "
      "DD jusqu'à 67 %, 12-16 mois négatifs/21). La decay 2025-2026 l'a tué — "
      "l'adaptateur 90 j est confirmé, et même lui ne le ressuscite pas à ces coûts.")
    A("- **mean_reversion** — la seule invariance vraie du lot est son WR : 38-52 % "
      "dans TOUS les régimes. Mais RR inversé (stop 150 / take 200) + frais = "
      "perdant partout (0-4/12, −38 à −72 %/an médians). L'invariant est le WR, "
      "pas le PnL. Seule piste de survie : RR non inversé + exécution maker "
      "(phase 2), sinon NUL.")
    A("- **breakout** — négatif quasi partout (1-2/12, −38 à −44 %/an médians en "
      "2021-2022) ; à peine l'équilibre en recovery 2023 (6/12, ~0 %) et la "
      "médiane +20 % de la période connue est portée par SOL seul (5/12 : queue "
      "SOL, pas un edge BTC/ETH). NUL en deep 1h à ces coûts.")
    A("- **funding_carry** — le seul positif d'UN régime : bear 2022 (9/12, "
      "+39 %/an médian) — accident du funding constant (le signe du funding EST "
      "son signal : +0,44 bps/8h → short permanent 5 ans). Re-résolution du sens "
      "par régime : le « collecteur » combat la tendance, −32 à −78 %/an partout "
      "ailleurs. Perdant structurel tel qu'implémenté (perp unhedged) ; le vrai "
      "carry delta-hedgé spot+perp est hors harnais.")
    A("- **funding_fade** — artefact (série synthétique) ; même ainsi, bruit "
      "autour de 0 au flux de trades.")
    A("- **volatility_harvesting** — artefact microstructure, non évaluable en 1h.")
    A("")
    A("**2. La preuve du mécanisme demandée (Q3) :** le bear 2022 récompense le "
      "short — mais PAS le short tradé. Le short PASSIF permanent imprime "
      "(+39 %/an médian, 9/12) ; le short ACTIF à stops 2 % (momentum V1_short) "
      "perd en bear (−18 %/an médian : whipsaw des rallies + frais). En bear, "
      "c'est l'exposition constante qui paie, pas le trading. Et sur bull 2021-H2 "
      "(question vol_spike) : RIEN ne survit au flux de trades — la fin de cycle "
      "2021 est le pire régime du lot après 2025-2026.")
    A("")
    A("**3. La decay 2025-2026 est générale, pas un artefact :** période connue = "
      "la pire pour 4 stratégies sur 6 (momentum 0/12, mean_reversion 0/12, carry "
      "0/12, breakout 5/12 à −3 %). L'adaptateur 90 j est nécessaire ; il n'est "
      "PAS suffisant à 1x frais taker sur 1h — les edges 1h « gratuits » "
      "n'existent plus sur majors.")
    A("")
    A("**4. Implications :** (a) corriger l'équité du harnais (booker stop+frais "
      "dans `bar_ret`) — priorité absolue, sinon le validateur nocturne sur-estime "
      "toutes les lanes ; (b) aucun des 6 n'entre au stack en l'état (0/12 sur la "
      "période connue : le test wallet séquentiel est inutile, les lanes sont "
      "mortes avant) ; (c) si l'adaptateur détecte un régime bear, la jambe short "
      "doit être PORTÉE (exposition constante, cf. carry bear 2022), pas tradée "
      "avec des stops serrés ; (d) ré-catégoriser au registre : momentum "
      "CONTEXTE (edge de cycle 2023-2024), breakout/funding_carry NUL en deep 1h, "
      "mean_reversion CONTEXTE (WR invariant, PnL tué par le RR), "
      "volatility_harvesting/funding_fade NUL hors phase 2.")
    A("")
    A("## Limites honnêtes")
    A("")
    A("1. **Funding modélisé** : sur 2021-2024 le funding est une hypothèse par régime (les manies 2021 ont vu des pointes 10-30 bps/8h que le modèle ne reproduit pas) ; par ailleurs la jambe funding n'existe que dans `bar_ret`, pas dans les trade_returns des modules directionnels (±0,4 bps/8h constants ≈ ±1-3 %/an, négligeable devant les écarts observés). Verdicts RELATIFS priment sur les ABSOLUS.")
    A("2. **Fills modèle** : stops remplis au prix du stop (optimiste sur les barres qui gapent — LUNA/FTX), takes comme limites (plausible). Le flux de trades est donc encore LÉGÈREMENT optimiste ; les conclusions négatives en sont renforcées, pas affaiblies.")
    A("3. **1h seulement** : les 15m/1m profonds (178k / 2,67M barres) = phase 2. Ce test juge les FAMILLES d'edges de la campagne, pas les lanes machine exactes (cascade/survivor/vol_spike : horizons plus fins, data plus fine).")
    A("4. **ASTER hors scope deep** : 1 an de données (2025-09 →), jugé par la campagne nocturne, pas ici.")
    A("5. **Attribution des trades** : par régime d'ENTRÉE (un trade entré fin de régime peut sortir dans le suivant) ; composition séquentielle des trades = positions non chevauchantes (stratégies à états).")
    A("6. Frais/slippage = modèle Aster actuel (taker 4 bps/jambe, carnet synthétique 50K) ; carnets 2021-2022 plus profonds sur majors (hypothèse conservatrice OK).")
    A("7. Bench random dégradé (50 tirages au lieu de 1000) : n'affecte pas les gates trades/sharpe/DD.")
    A("8. ROI composés sur des trades 1x non plafonnés : SOL (+10x en 2023, −94 % en 2022) domine les moyennes — lire les médianes des 3 majors, pas les moyennes.")
    A("")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
