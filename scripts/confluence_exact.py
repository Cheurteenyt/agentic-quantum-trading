#!/usr/bin/env python
"""LA CONFLUENCE EXACTE — la définition v5 du harnais dans le wallet réel.

La confluence vedette (74,4 % WR à horizon fixe, N=43) n'a jamais été
mesurée dans le wallet séquentiel avec SA définition exacte : le stack
utilisait une proxy (rate ≥ p90 + dev ≥ μ+3σ/720h). La définition v5 :
  funding qui ACCÉLÈRE (diff 3h du taux > 0, la foule empile des longs)
  + prix -3 %/24h (la première jambe)
  + prix ≥ +3σ au-dessus du vwap 7j (l'étirement du blow-off top)
→ short le sommet étiré pendant que la foule est encore longue.

Ce script mesure : WR réel, wallet séquentiel seul, et le SWAP dans le
stack (conf_exact à la place de la proxy) — les chiffres décident.

  .venv/bin/python scripts/confluence_exact.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.funding_align import align_funding_rate  # noqa: E402
from scripts.portfolio_sim import KDB, btc_regime_series, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, collect_funding_strategies, funding_hourly_all,
    run_stack, stamp_expanding_q66)

REPORTS = ROOT / "reports"
HOLD = 24


def collect_conf_exact(con: sqlite3.Connection,
                       fh: pd.DataFrame) -> list[dict]:
    """La confluence EXACTE v5 sur l'univers 1h complet."""
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' ORDER BY symbol")]
    events: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 800:
            continue
        fh_sym = fh[fh.symbol == sym]
        if fh_sym.empty:
            continue
        tp = (df["high"] + df["low"] + df["close"]) / 3
        # FIX F-039 : un sentinelle pd.NA sur un dénominateur nul fait
        # basculer la série en dtype OBJECT dès qu'une fenêtre roulante est
        # entièrement nulle (le cas réel : 8 symboles de l'univers ont une
        # fenêtre 168 sans volume), et l'astype(float) qui suit lève alors
        # TypeError: float() argument must be ... not 'NAType'.
        # float("nan") garde le dtype float64 : le dénominateur nul donne un
        # dev NaN (comparaison False) au lieu d'exploser.
        # paper_forward.py avait déjà été corrigé ainsi (PR-162) — le
        # correctif n'avait pas été propagé aux 2 autres occurrences.
        vwap = ((tp * df["volume"]).rolling(168).sum()
                / df["volume"].rolling(168).sum().replace(0, float("nan")))
        dev = ((df["close"] - vwap) / vwap).astype(float)
        # la confluence vedette v5 = ACCEL funding + ÉTIREMENT vwap — 2 jambes
        # (le -3%/24h de la définition à 3 jambes appartient à
        # funding_prix_divergence seule ; le header du rapport dit maintenant
        # la même chose). ronde 11 : helper blindé — funding_time NULL/dup/s
        # crashait le reindex nu ou muait l'accel en silence.
        aligned = align_funding_rate(fh_sym, df.index, limit=8)
        accel = aligned.diff(3) > 0
        mask = (accel & (dev > 3 * dev.rolling(168).std())).fillna(False)
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        opens = df["open"].values
        highs = df["high"].values
        for t in np.where(mask)[0]:
            ei = t + 1
            if ei + HOLD >= len(idx_ns) or t < 300:
                continue
            entry = opens[ei]
            if entry <= 0:
                continue
            exit_j = ei + HOLD - 1
            if exit_j >= len(idx_ns):
                continue
            exit_px = float(df["close"].values[exit_j])
            events.append({
                "sym": sym, "ts_ms": int(idx_ns[ei]), "strategy": "confluence",
                "lev": 3, "hold_h": HOLD, "fee_rt_bps": TAKER_RT,
                "entry": entry, "exit": exit_px,
                "price_ret_short": (entry - exit_px) / entry * 100,
                "fund_sign": 1,
                "mae_adverse": (highs[ei:exit_j + 1].max() - entry)
                / entry * 100,
            })
    events.sort(key=lambda e: e["ts_ms"])
    return events


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    fh_hourly = funding_hourly_all()
    events = collect_conf_exact(con, fh_raw)
    regime = btc_regime_series()
    from scripts.anti_liq import collect_featured
    cascade = collect_featured(regime, "majors")
    for e in cascade:
        e["strategy"] = "cascade"
        e["lev"] = 20
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(cascade)
    # C-B3 (ronde 11) : le seuil de gate était UN SEUL quantile calculé sur
    # les 70 % PREMIERS du sample puis appliqué à TOUS les événements — le
    # sizing au temps t voyait jusqu'à 70 % d'histoire FUTURE (look-ahead
    # plein, le motif corrigé dans stacked_portfolio). Le seuil est
    # maintenant EXPANDING posé par événement : au temps t il ne voit que
    # les scores antérieurs ; pendant le warm-up (< 30 obs) il est NaN et
    # l'event n'est PAS gaté (sémantique gate_expanding).
    cascade, _q66_last = stamp_expanding_q66(cascade)
    fdiv, conf_proxy = collect_funding_strategies(con)
    con.close()

    n = len(events)
    wr = (sum(1 for e in events if e["price_ret_short"] > 0) / max(n, 1) * 100)
    closed = [e for e in events if e["price_ret_short"] is not None]
    pnr = [e["price_ret_short"] for e in closed]

    alone = run_stack(events, CAPITAL, lambda e: 0.05, fh_hourly)
    mrows = monthly_rows(alone["trades"], CAPITAL)
    rois_m = [r["roi"] for r in mrows] if mrows else [0.0]

    # le SWAP dans le stack ×2 : conf_exact remplace la proxy
    def stack_policy(conf_events: list[dict]):
        allowed = {id(e) for e in conf_events}
        def fn(e: dict) -> float:
            s = e.get("strategy")
            if s == "cascade":
                sc = e.get("al_score", float("nan"))
                if np.isnan(sc):
                    return 0.05
                # C-B3 : seuil EXPANDING posé par event, pas le scalaire
                thr = e.get("_q66_asof", float("nan"))
                if np.isnan(thr):
                    return 0.045   # warm-up : pas de gate (gate_expanding)
                return 0.0 if sc >= thr else 0.045
            if s == "funding_div":
                return 0.015
            if s == "confluence":
                return 0.01 if id(e) in allowed else 0.0
            return 0.0
        return fn

    conf_ids = {id(e) for e in events}
    for e in conf_proxy:
        e["strategy"] = "confluence"
    all_base = sorted(cascade + fdiv + conf_proxy, key=lambda e: e["ts_ms"])
    stack_proxy = run_stack(all_base, CAPITAL, stack_policy(conf_proxy), fh_hourly)
    all_exact = sorted(cascade + fdiv + events, key=lambda e: e["ts_ms"])
    stack_exact = run_stack(all_exact, CAPITAL, stack_policy(events), fh_hourly)

    def policy2(fn):
        def f(e: dict) -> float:
            return fn(e) * 2
        return f
    stack_proxy2 = run_stack(all_base, CAPITAL, policy2(stack_policy(conf_proxy)),
                             fh_hourly)
    stack_exact2 = run_stack(all_exact, CAPITAL, policy2(stack_policy(events)),
                             fh_hourly)

    verdict = ("LA CONFLUENCE EXACTE SURVIT AU WALLET — swap adopté"
               if stack_exact2["balance"] > stack_proxy2["balance"] * 1.02
               else "LA PROXY RESTE MIEUX — le swap n'améliore pas le stack")

    lines = [
        "# LA CONFLUENCE EXACTE — la définition v5 dans le wallet séquentiel",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — funding accel + "
        f"dev > 3σ(168), short 24h, 3x taker. 2 jambes : le prix -3%/24h "
        f"de la v5 à 3 jambes appartient à funding_prix_divergence seule.", "",
        "## Le signal brut", "",
        f"- {n} événements sur 1 an (l'univers 1h complet)",
        f"- WR horizon-fixe 24h : **{wr:.1f} %**",
        f"- ret moyen : {np.mean(pnr):+.3f} %/trade (prix seul)", "",
        "## Le wallet séquentiel (100 $)", "",
        f"- SEULE (5 % flat) : ${alone['balance']:,.2f} "
        f"(ROI {(alone['balance']/CAPITAL-1)*100:+.1f} %, "
        f"DD {alone['max_dd']:.1f} %, {alone['n']} trades, "
        f"WR {alone['n_wins']/max(alone['n'],1)*100:.1f} %, "
        f"liq {alone['n_liq']})",
        (f"- ROI mensuel moyen : {np.mean(rois_m):+.1f} % "
         f"(pire {min(rois_m):+.1f} %)" if mrows else ""), "",
        "## Le SWAP dans le stack ×2", "",
        f"- stack avec la PROXY confluence : ${stack_proxy2['balance']:,.2f} "
        f"(DD {stack_proxy2['max_dd']:.1f} %)",
        f"- stack avec la CONFLUENCE EXACTE : **${stack_exact2['balance']:,.2f}** "
        f"(DD {stack_exact2['max_dd']:.1f} %)",
        f"- (×1 : proxy ${stack_proxy['balance']:,.2f} / "
        f"exact ${stack_exact['balance']:,.2f})", "",
        f"## VERDICT : {verdict}", "",
        "- le test tranche proxy vs exact sur le terrain qui compte :",
        "  le wallet séquentiel, pas le WR horizon-fixe.",
    ]

    out = REPORTS / f"confluence-exact-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[conf-exact] {n} évts, WR {wr:.1f} % | seule "
          f"${alone['balance']:,.2f} (DD {alone['max_dd']:.1f} %) | "
          f"stack ×2 : proxy ${stack_proxy2['balance']:,.2f} → "
          f"exact ${stack_exact2['balance']:,.2f}")
    print(f"[conf-exact] {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
