#!/usr/bin/env python
"""L'ÉCHELLE DE CONFLUENCE — le trade-off WR/N, rung par rung.

Le chemin mesuré vers un WR élevé : empiler des conditions
INDÉPENDANTES validées. Chaque rung de l'échelle ajoute une condition à
la cascade (le signal roi) et on mesure ce que ça fait au WR et au N :

  R1 : cascade seule (la référence)
  R2 : + prix étiré > 2σ au-dessus du vwap 7j
  R3 : + funding qui accélère (diff 3h > 0)
  R4 : étirement resserré à 3σ (la confluence exacte croisée cascade)

Le WR de chaque rung est mesuré sur l'issue 24h RÉELLE de chaque
événement, et le meilleur rung viable (N ≥ 30) passe au wallet
séquentiel. L'échelle est ORDONNÉE (conditions imbriquées) — pas un
cherry-pick de cellule.

  .venv/bin/python scripts/signal_ladder.py
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
from scripts.portfolio_sim import KDB, MAJORS, btc_regime_series, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, funding_hourly_all, run_stack)

REPORTS = ROOT / "reports"


def enrich(con: sqlite3.Connection, events: list[dict]) -> list[dict]:
    """Ajoute à chaque événement : l'étirement vwap (z-score) et l'accel
    funding as-of — les conditions des rungs."""
    fh = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    by_sym_fh: dict[str, pd.DataFrame] = {s: g for s, g in fh.groupby("symbol")}
    out = []
    for sym in MAJORS:
        evs = [e for e in events if e["sym"] == sym]
        if not evs:
            continue
        df = load_df(con, sym)
        if df is None:
            continue
        tp = (df["high"] + df["low"] + df["close"]) / 3
        # FIX F-039 : pd.NA fait basculer la série en object sur une fenêtre
        # roulante entièrement nulle (8 symboles le font réellement) et
        # l'astype(float) qui suit lève TypeError ... not 'NAType'.
        # float("nan") conserve float64. Même correctif que paper_forward
        # (PR-162) et confluence_exact, propagé ici.
        vwap = ((tp * df["volume"]).rolling(168).sum()
                / df["volume"].rolling(168).sum().replace(0, float("nan")))
        dev = ((df["close"] - vwap) / vwap).astype(float)
        dev_sd = dev.rolling(168).std()
        z = (dev / dev_sd).values
        fh_sym = by_sym_fh.get(sym)
        accel_ts = set()
        if fh_sym is not None and len(fh_sym):
            rate = fh_sym.set_index("funding_time")["rate"].astype(
                float).sort_index()
            rate.index = pd.to_datetime(rate.index, unit="ms")
            aligned = rate.reindex(df.index, method="ffill", limit=8)
            accel = (aligned.diff(3) > 0).fillna(False)
            idx_ns = df.index.astype("datetime64[ns]").asi8
            accel_ts = {int(idx_ns[t]) for t in np.where(accel)[0]}
        for e in evs:
            ei = int(np.searchsorted(
                df.index.astype("datetime64[ns]").asi8, e["ts_ms"],
                side="left"))
            e["vwap_z"] = float(z[ei]) if ei < len(z) else float("nan")
            e["funding_accel"] = e["ts_ms"] in accel_ts
            out.append(e)
    return out


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade"
        e["lev"] = 20
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)
    events = enrich(con, events)
    fh = funding_hourly_all()
    q66 = float(np.nanquantile(
        [e["al_score"] for e in events[:int(len(events) * 0.7)]], 2/3))

    # les rungs — conditions imbriquées
    rungs = [
        ("R1 : cascade seule", lambda e: True),
        ("R2 : + vwap étiré > 2σ", lambda e: e.get("vwap_z", 0) > 2),
        ("R3 : + funding accélère", lambda e: e.get("vwap_z", 0) > 2
         and e["funding_accel"]),
        ("R4 : étirement 3σ (cascade ∩ confluence exacte)",
         lambda e: e.get("vwap_z", 0) > 3 and e["funding_accel"]),
    ]
    lines = [
        "# L'ÉCHELLE DE CONFLUENCE — le trade-off WR/N",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{len(events)} cascades (majeures, 1 an), issue 24h réelle.", "",
        "| Rung | Condition | N | WR 24h | Ret moyen | Esp. marge 20x |",
        "|---|---|---|---|---|---|",
    ]
    best = None
    for label, cond in rungs:
        sel = [e for e in events if cond(e)]
        n = len(sel)
        wr = (sum(1 for e in sel if e["price_ret_short"] > 0)
              / max(n, 1) * 100)
        mean = (sum(e["price_ret_short"] for e in sel) / max(n, 1))
        margin = mean * 20 - MAKER_RT * 20 / 100
        lines.append(f"| {label} | {n} | {wr:.1f} % | {mean:+.2f} % | "
                     f"{margin:+.1f} % |")
        if n >= 30 and (best is None or wr > best[1]):
            best = (label, wr, sel)

    # le meilleur rung viable dans le wallet séquentiel
    wallet_lines = ["", "## Le wallet séquentiel (100 $) — rungs viables", ""]
    for label, wr, sel in ([best] if best else []):
        res = run_stack(sel, CAPITAL, lambda e: 0.075, fh)
        mrows = monthly_rows(res["trades"], CAPITAL)
        rois_m = [r["roi"] for r in mrows] if mrows else [0.0]
        wallet_lines.append(
            f"- **{label}** (WR échelle {wr:.1f} %) : 100 $ → "
            f"**${res['balance']:,.2f}** ({(res['balance']/CAPITAL-1)*100:+.0f} %/an, "
            f"DD {res['max_dd']:.1f} %, {res['n']} trades, "
            f"WR wallet {res['n_wins']/max(res['n'],1)*100:.1f} %, "
            f"liq {res['n_liq']}, mois moyen {np.mean(rois_m):+.1f} %, "
            f"pire {min(rois_m):+.1f} %)")

    lines += wallet_lines
    if best and best[1] >= 65:
        lines += ["", f"**LE RUNG QUALITÉ : {best[0]} à {best[1]:.1f} % de WR "
                  f"d'échelle** — candidat paper forward (le N grossit "
                  f"chaque semaine, le forward juge)."]
    else:
        lines += ["", "**AUCUN rung ne dépasse 65 % avec N ≥ 30** — la "
                  "montée du WR au-delà exige d'autres dimensions "
                  "(liq-storm, depth) que la série accumule."]

    out = REPORTS / f"signal-ladder-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[ladder] best: {best[0] if best else '—'} "
          f"WR {best[1]:.1f} % (N={len(best[2])})" if best else
          "[ladder] aucun rung viable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
