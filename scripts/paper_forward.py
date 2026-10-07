#!/usr/bin/env python
"""Paper-trading FORWARD — les 5 candidats jugés sur les données de demain.

Chaque nuit : détecte les événements frais (< 48h) des 5 signaux candidats
issus de la campagne v5 (au-dessus du drift, coûts+funding réels), ouvre un
paper trade à l'open suivant, et CLÔT les trades dont l'horizon est écoulé
avec les prix RÉELS. Le ledger cumulatif = le vrai juge : si un candidat ne
survit pas en forward, il sort — sans réécriture de l'histoire.

Ledger : klines.db:paper_trades. Rapport : reports/paper-forward-<date>.md
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import (  # noqa: E402
    load_df, price_signals, COST_PCT, HORIZONS,
)
from scripts import aster_indicators as ta  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"

# ——— LEVIER CASCADE MAJORS ASSERVI AU MAE (T8, pré-enregistré 01/10/2026,
# reports/aster_machine_deep_regimes.md) ———
# Règle gravée : levier ≤ 100/(MAE_pire_régime + 0,5) → 4x sur le cycle ;
# 10x SEULEMENT si le moniteur MAE 6 majors (the_machine.py →
# data/warehouse/mae_state.json) donne lev_safe >= 10. DÉFAUT SÛR = 4x :
# état absent, illisible ou périmé (> 8 j sans tir de la machine nocturne).
# Base inchangée (0.24) ; meme/survivor/vol_spike restent 1x.
def _cascade_majors_lever(state_path: Path | None = None) -> float:
    p = state_path if state_path is not None else (
        ROOT / "data" / "warehouse" / "mae_state.json")
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(str(st["updated_at"])))
        if age > timedelta(days=8):
            return 4.0   # périmé : le défaut SÛR
        return 10.0 if float(st["lev_safe"]) >= 10.0 else 4.0
    except Exception:
        return 4.0       # absent/illisible : le défaut SÛR

# les 5 candidats de la campagne v5 : (signal, horizon_h, direction)
CANDIDATES = [
    ("failed_ath_breakout_short", 1440, -1),   # le cycle de vie (v6, lent)
    ("funding_div_plus_vwap_short", 24, -1),   # la confluence vedette (v6)
    ("funding_div_plus_vwap_short", 168, -1),
    ("funding_prix_divergence_short", 12, -1),
    ("funding_extreme_contre_courant", 168, -1),
    ("vwap_extreme_reprise_short", 1440, -1),
    ("vwap_extreme_reprise_short", 2160, -1),
    ("sweep_liquidite_short", 2160, -1),
]
WINDOW_H = 48  # on détecte les événements des 48 dernières heures

# ——— LA SONDE P3 : fund7/vol7/liq24h loggés à CHAQUE activation de signal
# (les gradients mensuels de l'autopsie 27/09). Définitions EXACTES de
# mechanism_probe.py — importées, jamais réinventées :
#   fund7  = funding MOYEN 7j du symbole à l'activation, en % /8h
#            (mechanism_probe.fund7_at, fenêtre 7j en ms sur funding_history)
#   vol7   = ATR % roulant 7j MOYEN des 6 majeures
#            (mechanism_probe.vol7_series, asof au timestamp d'activation)
#   liq24h = notional SELL (longs liquidés) 24h glissantes, $ (probe L94-103)
# 0.0 si données absentes — la sonde ne bloque jamais un flux.
_PROBE_STATE: dict = {}


def probe_fields(con: sqlite3.Connection, sym: str, t0_ms: float) -> tuple:
    """(fund7, vol7, liq24h) au moment de l'activation t0_ms (ms)."""
    try:
        import numpy as np
        from scripts.mechanism_probe import fund7_at, vol7_series
        if "vol7" not in _PROBE_STATE:      # la série : une fois par run
            _PROBE_STATE["vol7"] = vol7_series(con)
        _v = _PROBE_STATE["vol7"]
        vol7 = (float(_v.asof(pd.Timestamp(t0_ms, unit="ms")))
                if len(_v) else 0.0)
        if pd.isna(vol7):
            vol7 = 0.0
        if "liq" not in _PROBE_STATE:
            liq = pd.read_sql_query(
                "SELECT event_time, notional FROM liq_events WHERE side='SELL'",
                con)
            _PROBE_STATE["liq"] = (
                liq["event_time"].values.astype(np.int64),
                liq["notional"].values.astype(float))
        _ts, _no = _PROBE_STATE["liq"]
        m = (_ts >= t0_ms - 24 * 3600 * 1000) & (_ts < t0_ms)
        return fund7_at(con, sym, t0_ms), vol7, float(_no[m].sum())
    except Exception as _e:
        print(f"[paper] sonde P3 ({sym}) : {_e}")
        return 0.0, 0.0, 0.0


# ——— LE GATE fund7 (MÉCANISME P3 VALIDÉ — PRÉ-ENREGISTRÉ le 30/09/2026) ———
# Sonde p2 (reports/aster_deep_regimes_p2.md, N=61, 29 fermés) : les shorts
# cascade/sweep activés en funding POSITIF élevé gagnent (fund7 ≥ 0,5 bps/8h
# → hit 50 %, ret méd +2,0 % ; manie > 1 bp → hit 100 % n=6) ; en funding
# négatif ils perdent (hit 44 %, ret −0,7 % — la foule déjà short = pas de
# carburant). UNITÉ VERIFIÉE sur les données : fund7_at retourne des % /8h
# (rate décimal ×100) et COUNT(fund7 > 0,005) sur paper_trades = 32/61,
# la reproduction exacte des « 32/61 à fund7 > 0,5 bps/8h » de p2 →
# le seuil exact dans l'échelle stockée = 0,005 %/8h (= 0,5 bps).
GATE_FUND7_MIN_PCT = 0.005   # 0,5 bps/8h
# Familles gate-d : les shorts CASCADE/SWEEP de la sonde uniquement.
# PAS machine_vol_spike_6h (fund7 méd −0,04 bps, pire famille — le gate
# les tuerait à tort). machine_cascade_majors / machine_deep_fast /
# cascade_funding_rank_low : hors sonde (aucun n=61) — non gate-d, le
# verdict 90 j tranchera. Les trades déjà ouverts ne sont PAS touchés.
GATE_FUND7_SIGNALS = frozenset({
    "machine_cascade_meme",    # cascade memecoins (n=23, méd +0,80 bps)
    "sweep_liquidite_short",   # sweep de liquidité (n=31, méd +0,66 bps)
})
GATE_STATS = {"checked": 0, "skipped": 0}


def fund7_gate_pass(name: str, sym: str, fund7_pct: float) -> bool:
    """True = le signal passe le gate fund7 (protocole pré-enregistré 30/09).

    Skip si fund7 ≤ 0,5 bps/8h : pas de carburant de cascade. fund7 = 0.0
    (données funding absentes) → skip : sans données on ne peut PAS
    confirmer le carburant, le gate est mécanisme-dépendant.
    """
    if name not in GATE_FUND7_SIGNALS:
        return True
    GATE_STATS["checked"] += 1
    if fund7_pct <= GATE_FUND7_MIN_PCT:
        GATE_STATS["skipped"] += 1
        print(f"[gate-fund7] {sym} fund7={fund7_pct:.4f} %/8h < 0,5 bps — "
              "skip (mécanisme P3, pré-enregistré 30/09)")
        return False
    return True


def funding_paid_pct(con: sqlite3.Connection, sym: str,
                     t0_ms: int, t1_ms: int) -> float:
    """FIX lot2 (F3) : le funding RÉELLEMENT applicable sur (entrée, sortie]
    — les taux signés de funding_history, en points de %. Remplace
    load_env_funding_stats (supprimée) dont la moyenne full-sample
    fabriquait un look-ahead : un trade recevait la moyenne de tout
    l'historique au lieu des taux de sa propre fenêtre."""
    rows = con.execute(
        "SELECT rate FROM funding_history WHERE symbol=? "
        "AND funding_time>? AND funding_time<=?",
        (sym, t0_ms, t1_ms)).fetchall()
    return sum(float(r[0]) for r in rows if r[0] is not None) * 100.0


def funding_div_mask(df: pd.DataFrame, fh_sym: pd.DataFrame) -> pd.Series:
    """funding_prix_divergence_short : funding qui accélère + prix -3 %/24h."""
    rate = fh_sym.set_index("funding_time")["rate"].astype(float).sort_index()
    rate.index = pd.to_datetime(rate.index, unit="ms")
    # FIX audit v3 (C16) : l'accélération = diff(3) sur les ÉVÉNEMENTS de
    # funding (3 prints) — l'ancien diff(3) sur la série horaire alignée
    # mesurait 3 HEURES, une signification différente par contrat (1h/4h/8h).
    accel_ev = rate.diff(3)
    aligned = accel_ev.reindex(df.index, method="ffill", limit=8)
    pchg = df["close"].pct_change(24)
    return ((aligned > 0) & (pchg < -0.03)).fillna(False)


def funding_extreme_events(fh_sym: pd.DataFrame) -> pd.DatetimeIndex:
    """funding_extreme_contre_courant : rate > p90 EXPANDING (anti look-ahead).
    Index en MILLISECONDES explicites (ns vs ms = le searchsorted plantait
    en lossy après le backfill profond du 25/09)."""
    rate = fh_sym["rate"].astype(float)
    ts = fh_sym["funding_time"].astype("int64")
    p90 = rate.expanding(min_periods=30).quantile(0.9)
    return pd.to_datetime(ts[(rate > p90).fillna(False)].values, unit="ms")


def funding_applied_pct(direction: int, rates_sum_pct: float) -> float:
    """Le funding appliqué au ret du trade, en points de % (payé < 0,
    reçu > 0) — FIX lot1 (F11) : la valeur n'était jamais persistée
    (0/659 lignes non nulles) et le ledger restait inauditable sur ce
    poste. Persistée, elle rend ret recomputable : ret = prix - coûts
    + funding_pct. FIX lot2 (F3) : l'entrée est la SOMME des taux réels
    de la fenêtre (funding_paid_pct), plus jamais une moyenne × hold."""
    return -direction * rates_sum_pct


def ensure_paper_schema(con: sqlite3.Connection) -> None:
    """Crée/migre paper_trades. FIX lot1 (F4) : horizon_h entre dans la PK —
    les candidats bi-horizons (24/168, 1440/2160) s'avaluaient mutuellement
    via le pré-check + INSERT OR IGNORE (l'horizon 2160 est resté à 0
    trades depuis l'origine). Migration idempotente : rebuild si l'ancienne
    PK 3-colonnes est détectée, colonnes et lignes préservées, DROP refusé
    si le compteur ne colle pas."""
    con.execute("""CREATE TABLE IF NOT EXISTS paper_trades (
        signal TEXT NOT NULL, symbol TEXT NOT NULL, horizon_h INTEGER NOT NULL,
        direction INTEGER NOT NULL, signal_ts INTEGER NOT NULL,
        entry_ts INTEGER NOT NULL, entry_price REAL NOT NULL,
        exit_ts INTEGER, exit_price REAL, ret_pct REAL,
        funding_pct REAL, status TEXT NOT NULL, created_at REAL NOT NULL,
        PRIMARY KEY (signal, symbol, signal_ts, horizon_h))""")
    pk = [r[1] for r in sorted(
        (r for r in con.execute("PRAGMA table_info(paper_trades)") if r[5]),
        key=lambda r: r[5])]
    if pk[:3] != ["signal", "symbol", "signal_ts"] or "horizon_h" in pk:
        return
    con.execute("ALTER TABLE paper_trades RENAME TO paper_trades_old_pk")
    old = [(r[1], r[2], r[3]) for r in con.execute(
        "PRAGMA table_info(paper_trades_old_pk)")]
    defs = ", ".join(f"{n} {t}{' NOT NULL' if nn else ''}" for n, t, nn in old)
    con.execute(f"CREATE TABLE paper_trades ({defs}, "
                "PRIMARY KEY (signal, symbol, signal_ts, horizon_h))")
    names = ", ".join(n for n, _, _ in old)
    n_old = con.execute(
        "SELECT COUNT(*) FROM paper_trades_old_pk").fetchone()[0]
    con.execute(f"INSERT INTO paper_trades ({names}) "
                f"SELECT {names} FROM paper_trades_old_pk")
    n_new = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
    if n_old != n_new:
        raise RuntimeError(
            f"migration paper_trades : {n_old} -> {n_new} lignes — DROP refusé")
    con.execute("DROP TABLE paper_trades_old_pk")
    # ——— sonde P3 (fund7/vol7/liq24h, les gradients de l'autopsie 27/09) :
    # 3 colonnes ajoutées en fin de table, idempotent. Ajout seul : le
    # tracker qubo_forward_tracker lit en ro avec colonnes nommées. ———
    for _ddl in ("ALTER TABLE paper_trades ADD COLUMN fund7 REAL",
                 "ALTER TABLE paper_trades ADD COLUMN vol7 REAL",
                 "ALTER TABLE paper_trades ADD COLUMN liq24h REAL"):
        try:
            con.execute(_ddl)
        except sqlite3.OperationalError as _e:
            if "duplicate column" not in str(_e).lower():
                raise


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    ensure_paper_schema(con)
    now = time.time()
    now_ms = int(now * 1000)
    since_ms = now_ms - WINDOW_H * 3600 * 1000

    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]
    fh = pd.read_sql_query("SELECT symbol, funding_time, rate FROM funding_history", con)
    btc = load_df(con, "BTCUSDT")

    opened = closed_n = 0
    for name, horizon, direction in CANDIDATES:
        for sym in sorted(symbols):
            df = load_df(con, sym)
            if df is None or len(df) < 400:
                continue
            fh_sym = fh[fh.symbol == sym]
            if name in ("funding_prix_divergence_short",
                        "funding_div_plus_vwap_short"):
                if fh_sym.empty:
                    continue
                mask = funding_div_mask(df, fh_sym)
                if name == "funding_div_plus_vwap_short":
                    tp = (df["high"] + df["low"] + df["close"]) / 3
                    # NaN (pas pd.NA) : le dénominateur nul doit donner un
                    # dev NaN (comparaison False), pas exploser astype(float)
                    # — le crash TypeError 'NAType' du nightly du 07/10 03:24
                    vwap = ((tp * df["volume"]).rolling(168).sum()
                            / df["volume"].rolling(168).sum().replace(0, float("nan")))
                    dev = ((df["close"] - vwap) / vwap).astype(float)
                    mask = mask & (dev > 3 * dev.rolling(168).std()).fillna(False)
                ev = df.index[mask]
            elif name == "funding_extreme_contre_courant":
                if fh_sym.empty:
                    continue
                ev = funding_extreme_events(fh_sym)
            else:
                sig = dict((n, (d, s)) for n, d, s in price_signals(df, btc))
                if name not in sig:
                    continue
                ev = df.index[sig[name][1].fillna(False)]
            # événements frais uniquement
            ev = pd.DatetimeIndex([t for t in ev if t.timestamp() * 1000 >= since_ms])
            for ts in ev:
                sig_ts = int(ts.timestamp() * 1000)
                if con.execute(
                    "SELECT 1 FROM paper_trades WHERE signal=? AND symbol=? "
                    "AND signal_ts=? AND horizon_h=?",
                    (name, sym, sig_ts, horizon)).fetchone():
                    continue
                i = int(df.index.searchsorted(ts, side="right"))
                if i >= len(df.index):
                    continue
                entry_i = i  # l'open de la bougie suivante = bougie i ici
                entry_ts = int(df.index[entry_i].timestamp() * 1000)
                entry_price = float(df["open"].iloc[entry_i])
                if entry_price <= 0:
                    continue
                exit_ts_ms = entry_ts + horizon * 3600 * 1000
                fund_col = None
                if now_ms >= exit_ts_ms:
                    # horizon déjà écoulé : clôture immédiate au prix réel
                    j = min(entry_i + horizon - 1, len(df.index) - 1)
                    exit_price = float(df["close"].iloc[j])
                    exit_ts = exit_ts_ms   # l'heure de prix réelle = entry + hold
                    hold_h = (exit_ts_ms - entry_ts) / 3600000.0
                    fund_col = round(funding_applied_pct(
                        direction,
                        funding_paid_pct(con, sym, entry_ts, exit_ts_ms)), 4)
                    ret = ((exit_price - entry_price) / entry_price * 100 * direction
                           - COST_PCT + fund_col)
                    status = "closed"
                    closed_n += 1
                else:
                    exit_price = exit_ts = ret = None
                    status = "open"
                    closed_n += 0
                f7, v7, l24 = probe_fields(con, sym, sig_ts)   # sonde P3
                if not fund7_gate_pass(name, sym, f7):
                    continue   # gate fund7 : pas de carburant → pas de trade
                con.execute(
                    "INSERT OR IGNORE INTO paper_trades (signal, symbol, "
                    "horizon_h, direction, signal_ts, entry_ts, entry_price, "
                    "exit_ts, exit_price, ret_pct, funding_pct, status, "
                    "created_at, fund7, vol7, liq24h) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (name, sym, horizon, direction, sig_ts, entry_ts, entry_price,
                     exit_ts, exit_price, ret, fund_col, status, now, f7, v7, l24))
                opened += 1

    # ——— le CANDIDAT QUALITÉ : cascade ∩ funding-rank-bas (25/09) ———
    # le rang cross-sectionnel du funding parmi les 6 majeures À L'INSTANT
    # du signal ; T1 (≤ 0,33) : WR 81 % backtest (n=21), ~2 trades/mois.
    # La définition vient d'anti_liq (le collecteur discipliné unique).
    try:
        import numpy as _np
        from scripts.anti_liq import add_rolling_scores, collect_featured
        from scripts.portfolio_sim import MAJORS as _MAJORS
        from scripts.portfolio_sim import btc_regime_series as _brs
        _regime = _brs()
        _casc = collect_featured(_regime, "majors")
        add_rolling_scores(_casc)
        _q66 = float(_np.nanquantile(
            [e.get("al_score", float("nan"))
             for e in _casc[:int(len(_casc) * 0.7)]], 2 / 3))
        _gated = [e for e in _casc
                  if not (_np.isfinite(e.get("al_score", float("nan")))
                          and e["al_score"] >= _q66)]
        _fts: dict[str, tuple[list, list]] = {}
        for s, t, r in con.execute(
                "SELECT symbol, funding_time, rate FROM funding_history "
                "ORDER BY funding_time"):
            try:
                t = int(t)
                ts, rt = _fts.setdefault(s, ([], []))
                ts.append(t * 10**6 if t > 10**11 else t * 10**9)
                rt.append(float(r))
            except (TypeError, ValueError):
                continue
        _fresh = []
        for e in _gated:
            t0 = e["ts_ms"]
            ranks, own = [], _np.nan
            for s in _MAJORS:
                ft = _fts.get(s)
                if not ft or len(ft[0]) < 5:
                    continue
                pos = int(_np.searchsorted(_np.array(ft[0]), t0,
                                           side="right")) - 1
                if pos < 0:
                    continue
                if s == e["sym"]:
                    own = ft[1][pos]
                ranks.append(ft[1][pos])
            rank = (float(_np.mean(_np.array(ranks) <= own))
                    if ranks and _np.isfinite(own) else float("nan"))
            if (_np.isfinite(rank) and rank <= 0.33
                    and t0 / 10**6 >= now_ms - WINDOW_H * 3600 * 1000):
                _fresh.append(e)
        for e in _fresh:
            sig_ts = int(e["ts_ms"])
            if con.execute(
                "SELECT 1 FROM paper_trades WHERE signal=? AND symbol=? "
                "AND signal_ts=? AND horizon_h=?",
                ("cascade_funding_rank_low", e["sym"], sig_ts, 24)).fetchone():
                continue
            sig_ms = sig_ts // 10**6          # ts_ms = des NS (nom hérité)
            f7, v7, l24 = probe_fields(con, e["sym"], sig_ms)   # sonde P3
            con.execute(
                "INSERT OR IGNORE INTO paper_trades (signal, symbol, "
                "horizon_h, direction, signal_ts, entry_ts, entry_price, "
                "exit_ts, exit_price, ret_pct, funding_pct, status, "
                "created_at, fund7, vol7, liq24h) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("cascade_funding_rank_low", e["sym"], 24, -1, sig_ms,
                 sig_ms, float(e["entry"]), None, None, None, None,
                 "open", now, f7, v7, l24))
            opened += 1
    except Exception as _e:
        print(f"[paper] candidat qualité : {_e}")

    # ——— LES FLUX DE LA MACHINE (le forward du portefeuille officiel) ———
    # cascade majeurs 10x gated + cascade memecoins 1x + survivor long 1x
    # + vol_spike_6h 1x (expérimental, flag --vol-spike côté machine).
    # Les trades paper portent le ret au niveau PRIX ; la table forward du
    # rapport applique les tailles réelles (base × levier) à l'agrégation.
    try:
        from scripts.the_machine import collect_meme as _cm
        from scripts.full_arsenal_2 import collect as _ca
        from scripts.anti_liq import add_rolling_scores as _ars
        from scripts.anti_liq import collect_featured as _cf
        from scripts.portfolio_sim import btc_regime_series as _brs
        _regime = _brs()
        _casc = _cf(_regime, "majors")
        _ars(_casc)
        _q66 = float(_np.nanquantile(
            [e.get("al_score", float("nan"))
             for e in _casc[:int(len(_casc) * 0.7)]], 2 / 3))
        _streams = {
            "machine_cascade_majors": [
                e for e in _casc
                if not (_np.isfinite(e.get("al_score", float("nan")))
                        and e["al_score"] >= _q66)],
            "machine_cascade_meme": _cm(con),
            "machine_survivor_long": _ca(con, fh).get(
                "survivor_long_72h", []),
        }
        _specs = {"machine_cascade_majors": (24, -1),
                  "machine_cascade_meme": (24, -1),
                  "machine_survivor_long": (72, +1)}
        # flux 4 (expérimental --vol-spike côté machine) : vol_spike_6h,
        # même collecteur p5 validé (seuils non re-tunés) — direction PAR
        # ÉVÉNEMENT (fund_sign +1 = short → direction -1).
        try:
            from scripts.p5_frequency_test import collect_vol_spike as _cvs
            _streams["machine_vol_spike_6h"] = _cvs(con, hold=6)
        except Exception as _e2:
            print(f"[paper] vol_spike collect : {_e2}")
            _streams["machine_vol_spike_6h"] = []
        _specs["machine_vol_spike_6h"] = (6, None)   # None = dir par event
        # flux 5 (PROMOTION 29/09 — la profonde-rapide, CANDIDAT n°1 du
        # cascade) : 2 bougies r1<0 accélérées, depth >= 3 %, short, hold
        # 24h, lev 7,5x. Générateur dédié deep_fast_signals.py (l'entrée =
        # la close de la bougie du signal) ; idempotent via paper_trades.
        try:
            from scripts.deep_fast_signals import collect_deep_fast as _cdf
            _streams["machine_deep_fast"] = _cdf(con)
        except Exception as _e3:
            print(f"[paper] deep_fast collect : {_e3}")
            _streams["machine_deep_fast"] = []
        _specs["machine_deep_fast"] = (24, -1)
        _fresh_n = 0
        for _sig, _evs in _streams.items():
            _hold, _dir = _specs[_sig]
            for e in _evs:
                _dir_e = (-int(e.get("fund_sign", 1)) if _dir is None
                          else _dir)
                sig_ms = int(e["ts_ms"]) // 10**6   # ts_ms = des NS
                if sig_ms < now_ms - WINDOW_H * 3600 * 1000:
                    continue
                if con.execute(
                    "SELECT 1 FROM paper_trades WHERE signal=? AND symbol=? "
                    "AND signal_ts=? AND horizon_h=?",
                    (_sig, e["sym"], sig_ms, _hold)).fetchone():
                    continue
                _f7, _v7, _l24 = probe_fields(con, e["sym"], sig_ms)
                if not fund7_gate_pass(_sig, e["sym"], _f7):
                    continue   # gate fund7 : pas de carburant → pas de trade
                con.execute(
                    "INSERT OR IGNORE INTO paper_trades (signal, symbol, "
                    "horizon_h, direction, signal_ts, entry_ts, entry_price, "
                    "exit_ts, exit_price, ret_pct, funding_pct, status, "
                    "created_at, fund7, vol7, liq24h) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (_sig, e["sym"], _hold, _dir_e, sig_ms, sig_ms,
                     float(e["entry"]), None, None, None, None, "open", now,
                     _f7, _v7, _l24))
                _fresh_n += 1
        if _fresh_n:
            print(f"[paper] machine streams : {_fresh_n} ouvertures fraîches")
    except Exception as _e:
        print(f"[paper] machine streams : {_e}")

    # clôture des paper trades ouverts dont l'horizon est atteint
    open_rows = con.execute(
            "SELECT rowid, signal, symbol, horizon_h, direction, entry_ts, "
            "entry_price FROM paper_trades WHERE status='open'").fetchall()
    for row in open_rows:
        rid, name, sym, horizon, direction, entry_ts, entry_price = row
        df = load_df(con, sym)
        if df is None:
            continue
        exit_ts_ms = entry_ts + horizon * 3600 * 1000
        if now_ms < exit_ts_ms:
            continue
        target = pd.Timestamp(exit_ts_ms, unit="ms")
        # convention backtest (closes[ei+hold-1]) : le prix à T+hold est la
        # close de la bougie ouverte à T+hold-1h — pas celle d'après.
        j = int(df.index.searchsorted(target, side="left")) - 1
        j = max(min(j, len(df.index) - 1), 0)
        exit_price = float(df["close"].iloc[j])
        # PR-167 (P2) : un symbole en trou/délisté clampe j à sa dernière
        # bougie — le prix devient STALE alors que exit_ts reste exact
        # (ret faux en silence) ; on l'annonce
        if int(df.index[j].value // 10**6) < exit_ts_ms - 3_600_000:
            print(f"  ! {name}/{sym} : exit STALE (dernière bougie "
                  f"{df.index[j]} < sortie {exit_ts_ms}) — ret non fiable")
        exit_ts = exit_ts_ms
        hold_h = (exit_ts_ms - entry_ts) / 3600000.0
        fund_col = round(funding_applied_pct(
            direction, funding_paid_pct(con, sym, entry_ts, exit_ts_ms)), 4)
        ret = ((exit_price - entry_price) / entry_price * 100 * direction
               - COST_PCT + fund_col)
        con.execute("UPDATE paper_trades SET exit_ts=?, exit_price=?, ret_pct=?, "
                    "funding_pct=?, status='closed' WHERE rowid=?",
                    (exit_ts, exit_price, round(ret, 4), fund_col, rid))
        closed_n += 1
    con.commit()

    # ——— rapport ———
    rows = con.execute("SELECT signal, horizon_h, status, COUNT(*), "
                       "AVG(ret_pct) FROM paper_trades GROUP BY 1,2,3").fetchall()
    lines = [f"# Paper Forward — {datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC",
             "Les 5 candidats de la campagne v5 jugés sur les données fraîches.",
             f"Cette exécution : {opened} ouvertures, {closed_n} clôtures.",
             f"Gate fund7 (pré-enregistré 30/09) : {GATE_STATS['checked']} "
             f"contrôles, {GATE_STATS['skipped']} skips.", "",
             "| Candidat | H | Statut | N | WR | Ret moyen |", "|---|---|---|---|---|---|"]
    for sig, h, status, n, avg in rows:
        wr = con.execute("SELECT AVG(ret_pct > 0) FROM paper_trades "
                         "WHERE signal=? AND horizon_h=? AND status=?",
                         (sig, h, status)).fetchone()[0]
        wr_s = f"{wr*100:.0f} %" if wr is not None else "—"
        avg_s = f"{avg:+.2f} %" if avg is not None else "—"
        lines.append(f"| {sig} | +{h}h | {status} | {n} | {wr_s} | {avg_s} |")
    # cumul par candidat (closed uniquement)
    lines += ["", "## Cumul forward (closed uniquement)", ""]
    for name, horizon, _d in CANDIDATES:
        # PR-167 (P2) : le filtre HORIZON — sans lui, les bi-horizons
        # (24/168, 1440/2160) affichaient des lignes +Xh identiques
        r = con.execute("SELECT COUNT(*), AVG(ret_pct>0), AVG(ret_pct), "
                        "SUM(ret_pct) FROM paper_trades WHERE signal=? "
                        "AND horizon_h=? "
                        "AND status='closed'", (name, horizon)).fetchone()
        if r[0]:
            lines.append(f"- **{name} +{horizon}h** : {r[0]} trades, "
                         f"WR {r[1]*100:.0f} %, moyen {r[2]:+.2f} %, "
                         f"cumulé {r[3]:+.2f} %")
    # ——— LE PORTEFEUILLE MACHINE en forward (les tailles réelles) ———
    # levier majors asservi au MAE (T8, 01/10/2026) : 4x défaut sûr,
    # 10x si le moniteur MAE 6 majors donne lev_safe >= 10.
    _lev = {"machine_cascade_majors": _cascade_majors_lever(),
            "machine_cascade_meme": 1, "machine_survivor_long": 1,
            "machine_vol_spike_6h": 1, "machine_deep_fast": 7.5}
    from scripts.the_machine import MACHINE_K as _machine_k
    # PR-167 (P1 couche argent) : les bases forward taillées à l'IDENTIQUE
    # du backtest machine (×K) — l'ancien forward taillait aux bases
    # brutes : le spread QUBO−MAIN mesurait en partie « survivor ×2 »,
    # pas les poids. deep_fast n'est pas un flux machine (pas de K).
    _base = {"machine_cascade_majors": 0.24 * _machine_k,
             "machine_cascade_meme": 0.10 * _machine_k,
             "machine_survivor_long": 0.10 * _machine_k,
             "machine_vol_spike_6h": 0.10 * _machine_k,
             "machine_deep_fast": 0.10}
    _mrows = con.execute(
        "SELECT signal, symbol, direction, entry_ts, exit_ts, exit_price, "
        "entry_price, ret_pct, status FROM paper_trades "
        "WHERE signal LIKE 'machine_%' "
        "ORDER BY entry_ts, rowid").fetchall()
    _bal = 100.0
    _peak = _bal
    _mdd = 0.0
    _fmonth: dict[str, dict] = {}
    _busy: dict[str, int] = {}   # créneaux run_stack : 1 slot par flux
    _nplayed = 0
    for (sig, sym, d, ets, xts, xp, ep, ret, st) in _mrows:
        if _busy.get(sig, -(1 << 62)) > ets:
            continue             # flux occupé à l'entrée : non joué (run_stack)
        _busy[sig] = xts if xts is not None else (1 << 62)
        if st != "closed" or ret is None:
            continue             # ouvert : occupe le slot, PnL latent non compté
        _nplayed += 1
        frac = ret * _base.get(sig, 0.1) * _lev.get(sig, 1) / 100.0
        _bal *= (1 + frac)
        _peak = max(_peak, _bal)
        _mdd = max(_mdd, (_peak - _bal) / _peak * 100)
        m = datetime.fromtimestamp(xts / 1000, tz=timezone.utc).strftime("%Y-%m")
        fm = _fmonth.setdefault(m, {"roi": 0.0, "n": 0})
        fm["roi"] += frac * 100
        fm["n"] += 1
    _len_m = _nplayed
    _lines_m = [f"- Balance forward (100 $ →) : **${_bal:,.2f}** "
                f"sur {_len_m} trades clôturés, "
                f"DD forward {_mdd:.1f} %"]
    for m in sorted(_fmonth):
        fm = _fmonth[m]
        _lines_m.append(f"- {m} : {fm['roi']:+.1f} % ({fm['n']} trades)")
    lines += ["", "## LE PORTEFEUILLE MACHINE EN FORWARD (tailles réelles)", ""]
    lines += _lines_m
    _open_n = con.execute(
        "SELECT COUNT(*) FROM paper_trades WHERE "
        "signal LIKE 'machine_%' AND status='open'").fetchone()[0]
    lines += ["", f"Machine trades ouverts : {_open_n}"]

    out = (REPORTS / f"paper-forward-{datetime.now(timezone.utc):%Y-%m-%d-%H%M}.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[paper] {opened} ouvertures, {closed_n} clôtures -> {out}")
    _gs = GATE_STATS
    _gpct = 100.0 * _gs["skipped"] / _gs["checked"] if _gs["checked"] else 0.0
    print(f"[gate-fund7] run : {_gs['checked']} contrôles, "
          f"{_gs['skipped']} skips ({_gpct:.0f} %) — le taux de skip = "
          "la métrique du gate")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
