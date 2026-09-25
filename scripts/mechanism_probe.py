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
    for e in events:
        t0_ms = e["ts_ms"] / 10**6
        m = (sell_ts >= t0_ms - WIN_MS) & (sell_ts < t0_ms)
        storm_no = float(sell_no[m].sum())
        storm_n = int(m.sum())
        rows.append({**e, "storm_no": storm_no, "storm_n": storm_n})

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
        "**Lecture** : si TEMPÊTE > CALME en continuation (et MAE contenue),",
        "le mécanisme cascade-de-marges est RÉEL — les longs liquidés",
        "nourrissent la chute. Si CALME ≥ TEMPÊTE, nos cascades sont des",
        "patterns de prix sans ancrage d'acteurs. N de sonde : pas un",
        "verdict — le script se re-joue chaque nuit et N grossit.", "",
        "## Par cascade (détail)", "",
        "| Symbole | Date | Notional longs liq 24h | Continuation 24h | MAE |",
        "|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: -x["storm_no"])[:14]:
        d = datetime.fromtimestamp(r["ts_ms"] / 10**9, tz=timezone.utc)
        lines.append(
            f"| {r['sym']} | {d:%d/%m %H:%M} | ${r['storm_no']:,.0f} "
            f"({r['storm_n']} évts) | {r['price_ret_short']:+.2f} % | "
            f"{r['mae_adverse']:.2f} % |")

    out = REPORTS / f"mechanism-probe-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[probe] {len(rows)} cascades | TEMPÊTE {r_hot:+.3f} % (n={n_hot}) "
          f"vs CALME {r_calm:+.3f} % (n={n_calm}) | corr {corr:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
