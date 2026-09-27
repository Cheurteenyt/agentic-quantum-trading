#!/usr/bin/env python
"""LA SONDE DE MÉCANISME — la cascade coïncide-t-elle avec les liquidations ?

La question du user : nos indicateurs détectent-ils des VRAIS mouvements
(les acteurs) ou des ombres statistiques ? Le test : croiser chaque
cascade (majeures) avec les liquidations DIRECTES (forceOrder 24/7) de
la fenêtre précédente. Si les cascades « en tempête de longs liquidés »
continuent plus fort que les cascades sur livre calme, le mécanisme de
cascade de marges est RÉEL — et le conditionnement devient un indicateur
ancré mécaniquement, pas une story.

N honnête : la série liq_events démarre le 21/09 → ~4-6 jours → une
vingtaine de cascades complètes. C'est une SONDE (direction du signal),
pas un verdict. Elle est re-jouée chaque nuit : quand N aura grossi, la
sonde devient verdict.

  .venv/bin/python scripts/mechanism_probe.py
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

from scripts.anti_liq import collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.portfolio_sim import KDB, MAJORS, btc_regime_series  # noqa: E402

REPORTS = ROOT / "reports"
WIN_MS = 24 * 3600 * 1000       # la tempête = les 24h AVANT le signal (ms)
WIN7_MS = 7 * 24 * 3600 * 1000  # les 7 jours glissants (fund7, vol7)


def fund7_at(con: sqlite3.Connection, sym: str, t0_ms: float) -> float:
    """fund7 : le funding MOYEN 7j du symbole à l'activation (en % / 8h).

    Le séparateur n°1 de l'autopsie 27/09 (d=+0,98 sur les mois faibles) :
    un funding élevé ex-ante = la foule paye pour rester long → carburant
    de cascade. 0.0 si pas de données (jamais bloquer la sonde).
    """
    row = con.execute(
        "SELECT AVG(rate) FROM funding_history "
        "WHERE symbol = ? AND funding_time >= ? AND funding_time < ?",
        (sym, t0_ms - WIN7_MS, t0_ms)).fetchone()
    return float(row[0]) * 100 if row and row[0] is not None else 0.0


def vol7_series(con: sqlite3.Connection) -> pd.Series:
    """vol7 : l'ATR % roulant 7j MOYEN des majeures (série temporelle).

    Le séparateur n°3 de l'autopsie : vol7 bas en janvier = les mois faibles.
    ATR(1) % sur les bougies 1h, moyenne glissante 7j, puis moyenne
    inter-majeures → une valeur ex-ante à chaque timestamp d'activation.
    """
    parts = []
    for sym in MAJORS:
        df = load_df(con, sym)
        if df is None:
            continue
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
        atr_pct = (tr / df["close"] * 100).rolling("7D").mean()
        parts.append(atr_pct.rename(sym))
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, axis=1).mean(axis=1).dropna()


def main() -> int:
    con = sqlite3.connect(KDB)
    lo, hi, n_liq = con.execute(
        "SELECT MIN(event_time), MAX(event_time), COUNT(*) "
        "FROM liq_events").fetchone()
    if not lo or n_liq < 50:
        print("[probe] série liq trop jeune, patiente")
        return 1
    liq = pd.read_sql_query(
        "SELECT symbol, side, event_time, notional FROM liq_events", con)

    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    # ts_ms contient des NS (nom hérité) — convertir en ms pour liq_events
    events = [e for e in events
              if lo - WIN_MS <= e["ts_ms"] / 10**6 <= hi]
    liq_sell = liq[liq.side == "SELL"]      # un long liquidé
    sell_ts = liq_sell["event_time"].values.astype(np.int64)
    sell_no = liq_sell["notional"].values.astype(float)

    rows = []
    vol7 = vol7_series(con)
    for e in events:
        t0_ms = e["ts_ms"] / 10**6
        m = (sell_ts >= t0_ms - WIN_MS) & (sell_ts < t0_ms)
        liq24h = float(sell_no[m].sum())          # notional SELL 24h glissantes
        storm_n = int(m.sum())
        rows.append({**e, "liq24h": liq24h, "storm_no": liq24h,
                     "storm_n": storm_n,
                     "fund7": fund7_at(con, e["sym"], t0_ms),
                     "vol7": float(vol7.asof(pd.Timestamp(t0_ms, unit="ms")))
                     if len(vol7) else 0.0})

    if len(rows) < 10:
        print(f"[probe] seulement {len(rows)} cascades dans la fenêtre liq — "
              f"trop jeune, patiente")
        return 1

    storms = np.array([r["storm_no"] for r in rows], dtype=float)
    rets = np.array([r["price_ret_short"] for r in rows], dtype=float)
    maes = np.array([r["mae_adverse"] for r in rows], dtype=float)
    med = float(np.median(storms[storms > 0])) if (storms > 0).any() else 0.0
    hot = storms >= med
    calm = ~hot

    def stats(mask: np.ndarray) -> tuple[int, float, float]:
        nn = int(mask.sum())
        return (nn,
                float(np.mean(rets[mask])) if nn else 0.0,
                float(np.mean(maes[mask])) if nn else 0.0)

    n_hot, r_hot, m_hot = stats(hot)
    n_calm, r_calm, m_calm = stats(calm)
    # la corrélation brute storm ↔ continuation
    corr = float(np.corrcoef(np.log1p(storms), rets)[0, 1]) if len(rows) > 3 else 0.0

    # les séparateurs de l'autopsie 27/09, corrélés à la continuation
    fund7s = np.array([r["fund7"] for r in rows], dtype=float)
    vol7s = np.array([r["vol7"] for r in rows], dtype=float)

    def xcorr(arr: np.ndarray) -> float:
        if len(rows) > 3 and float(np.std(arr)) > 0:
            return float(np.corrcoef(arr, rets)[0, 1])
        return 0.0

    c_fund, c_vol = xcorr(fund7s), xcorr(vol7s)

    lines = [
        "# LA SONDE DE MÉCANISME — cascade × liquidations directes",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{n_liq} liquidations ({datetime.fromtimestamp(lo/1000, tz=timezone.utc):%d/%m} "
        f"→ {datetime.fromtimestamp(hi/1000, tz=timezone.utc):%d/%m}), "
        f"{len(rows)} cascades complètes dans la fenêtre.", "",
        "## Cascades en tempête (≥ médiane de notional longs liquidés 24h)", "",
        "| Groupe | N | Continuation 24h (short) | MAE moyenne |", "|---|---|---|---|",
        f"| TEMPÊTE | {n_hot} | {r_hot:+.3f} % | {m_hot:.2f} % |",
        f"| CALME | {n_calm} | {r_calm:+.3f} % | {m_calm:.2f} % |",
        f"| Corrélation log(1+storm) ↔ continuation | {corr:+.3f} | | |", "",
        "## Les séparateurs de l'autopsie (ex-ante, par activation)", "",
        "| Champ | Médiane | Corrélation ↔ continuation 24h |", "|---|---|---|",
        f"| fund7 (funding moyen 7j, % /8h) | {np.median(fund7s):+.4f} | {c_fund:+.3f} |",
        f"| liq24h (notional SELL 24h, $) | ${np.median(storms):,.0f} | {corr:+.3f} |",
        f"| vol7 (ATR %% 7j des majeures) | {np.median(vol7s):.3f} | {c_vol:+.3f} |", "",
        "**Lecture** : si TEMPÊTE > CALME en continuation (et MAE contenue),",
        "le mécanisme cascade-de-marges est RÉEL — les longs liquidés",
        "nourrissent la chute. Si CALME ≥ TEMPÊTE, nos cascades sont des",
        "patterns de prix sans ancrage d'acteurs. N de sonde : pas un",
        "verdict — le script se re-joue chaque nuit et N grossit.", "",
        "## Par cascade (détail)", "",
        "| Symbole | Date | liq24h ($) | fund7 %/8h | vol7 % | Continuation 24h | MAE |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: -x["storm_no"])[:14]:
        d = datetime.fromtimestamp(r["ts_ms"] / 10**9, tz=timezone.utc)
        lines.append(
            f"| {r['sym']} | {d:%d/%m %H:%M} | ${r['liq24h']:,.0f} "
            f"({r['storm_n']} évts) | {r['fund7']:+.4f} | {r['vol7']:.3f} | "
            f"{r['price_ret_short']:+.2f} % | {r['mae_adverse']:.2f} % |")

    out = REPORTS / f"mechanism-probe-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[probe] {len(rows)} cascades | TEMPÊTE {r_hot:+.3f} % (n={n_hot}) "
          f"vs CALME {r_calm:+.3f} % (n={n_calm}) | corr {corr:+.3f} | "
          f"corr fund7 {c_fund:+.3f}, vol7 {c_vol:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
