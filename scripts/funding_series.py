"""La vérité funding du projet : les taux RÉELS indexés par horodatage.

FIX lot2 (F3 + F12) : les simulateurs chargeaient sum(rates)/len(rates)/8 —
une moyenne FULL-SAMPLE appliquée à chaque trade historique (un trade 2022
recevait la moyenne 2022-2026 : du look-ahead pur) et l'intervalle de
funding était supposé 8h partout. L'intégration as-of ne compte que les
taux réellement applicables pendant (entrée, sortie], et l'intervalle est
MESURÉ (médiane des gaps), jamais supposé.

Le nom historique `funding_hourly_all` est conservé par ses appelants
(20+ fichiers passent le dict à run_stack sans l'ouvrir) : il retourne
désormais des FundingSeries — run_stack / run_sim consomment via
sum_pct_between, avec un shim documenté pour les rares dicts float legacy.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

KDB = Path(__file__).resolve().parents[1] / "data" / "warehouse" / "klines.db"


class FundingSeries:
    """Les taux de funding d'un symbole, triés par horodatage (ms).

    rates_pct porte le taux EN POINTS DE % (rate × 100) : sommer la fenêtre
    donne directement les % à appliquer au notionnel.
    """

    __slots__ = ("times_ms", "rates_pct", "interval_h")

    def __init__(self, times_ms, rates_pct, interval_h: float):
        self.times_ms = times_ms
        self.rates_pct = rates_pct
        self.interval_h = interval_h

    @classmethod
    def from_rows(cls, rows) -> "FundingSeries":
        """rows = [(funding_time_ms, rate_decimal)], ordre quelconque.

        interval_h = la médiane des gaps observés (F12 : première classe —
        les intervalles Aster ne sont pas universellement 8h)."""
        rows = sorted(rows)
        if not rows:
            raise ValueError("FundingSeries vide : aucune observation funding")
        # FIX v19 (№14) : dédupliquer les timestamps — deux lignes avec le
        # même funding_time additionnaient le taux DEUX FOIS dans cumsum
        seen = set()
        deduped = []
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                deduped.append(r)
            # sinon : doublon ignoré (le premier gagne)
        rows = deduped
        t = np.array([float(r[0]) for r in rows], dtype=np.float64)
        v = np.array([float(r[1]) * 100.0 for r in rows], dtype=np.float64)
        gaps_h = np.diff(t)[np.diff(t) > 0] / 3_600_000.0
        interval_h = float(np.median(gaps_h)) if len(gaps_h) else 8.0
        return cls(t, v, interval_h)

    def sum_pct_between(self, t0_ms: float, t1_ms: float) -> float:
        """Σ des taux applicables sur (t0, t1] — le funding réellement payé.

        Rien avant la première observation, rien après la dernière : pas de
        taux fabriqué, pas de taux postérieur à la sortie (anti look-ahead).
        """
        if t1_ms <= t0_ms or not len(self.times_ms):
            return 0.0
        k0 = int(np.searchsorted(self.times_ms, t0_ms, side="right"))
        k1 = int(np.searchsorted(self.times_ms, t1_ms, side="right"))
        return float(self.rates_pct[k0:k1].sum())

    def rate_asof(self, ts_ms: float) -> float | None:
        """Le dernier taux CONNU à ts (prints ≤ ts), en points de %.

        FIX audit v3 (C6/C7) : l'as-of STRICT — jamais d'interpolation.
        Entre deux prints, le taux connu est le premier : un print futur
        ne peut strictement rien changer à une décision passée.
        """
        if not len(self.times_ms):
            return None
        k = int(np.searchsorted(self.times_ms, ts_ms, side="right")) - 1
        return float(self.rates_pct[k]) if k >= 0 else None


def funding_series_for(symbol: str, db_path: Path | None = None) -> FundingSeries:
    """La série d'UN symbole — le loader ciblé pour la comptabilité par trade."""
    path = Path(db_path) if db_path else KDB
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT funding_time, rate FROM funding_history "
            "WHERE symbol=? ORDER BY funding_time", (symbol,)).fetchall()
    finally:
        con.close()
    if not rows:
        raise ValueError(f"aucun funding_history pour {symbol}")
    return FundingSeries.from_rows(rows)


def funding_series_all(db_path: Path | None = None) -> dict[str, FundingSeries]:
    """L'état funding de TOUS les symboles — LE loader unique du projet.

    Remplace les moyennes full-sample (l'ancien corps de funding_hourly_all
    dans stacked_portfolio et funding_hourly_map dans anti_liq).
    """
    path = Path(db_path) if db_path else KDB
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    out: dict[str, FundingSeries] = {}
    try:
        for sym, in con.execute("SELECT DISTINCT symbol FROM funding_history"):
            rows = con.execute(
                "SELECT funding_time, rate FROM funding_history "
                "WHERE symbol=? ORDER BY funding_time", (sym,)).fetchall()
            if rows:
                out[sym] = FundingSeries.from_rows(rows)
    finally:
        con.close()
    return out
