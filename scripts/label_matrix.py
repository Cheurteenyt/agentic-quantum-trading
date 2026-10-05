#!/usr/bin/env python3
"""LE FAST RESEARCH KERNEL — Research OS PR 4 (brief V3 §15-26).

La matrice de labels pré-calculés : pour chaque barre 1h de chaque symbole,
les rendements futurs à H horizons + les excursions (high/low max) + le
funding cumulé de la fenêtre — calculés UNE FOIS, cachés par hash, réutilisés
par toutes les découvertes.

Le gain (brief §18) : après le kernel, tester « range_z > 3 » vs « range_z > 4 »
est une statistique conditionnelle sur la matrice — plus aucun recalcul de
trajectoire de marché. Discovery devient un problème de masques, pas de
backtests.

Convention (celle du repo, gelée) :
  - entry = l'OPEN de la barre de ligne i (la décision est prise au close
    de i-1, exécution à l'open de i) ;
  - ret_H = prix : close(i+H-1) / open(i) - 1, en % — le CÔTÉ position est
    appliqué par l'appelant (short = -ret) ;
  - hi_H / lo_H = max(high)/open - 1 et min(low)/open - 1 sur [i, i+H-1] —
    MAE short = hi_H, MAE long = -lo_H (l'appelant dérive) ;
  - fund_H = Σ des taux (points de %) sur (open(i), open(i+H)] — as-of par
    construction (FundingSeries) ;
  - les H dernières barres d'un symbole portent des labels NaN (futur
    inexistant — jamais fabriqué).

Cache : data/cache/labels/<label_hash>/<symbol>.npz où label_hash =
sha256(snapshot_id + horizons + LABEL_VERSION). Invalidation : changer la
convention ou les horizons change le hash — jamais de mélange silencieux.

    python scripts/label_matrix.py --symbols BTCUSDT,ETHUSDT --horizons 6,24,72
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.funding_series import FundingSeries, funding_series_all  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
CACHE = ROOT / "data" / "cache" / "labels"
# v2 : fix unité funding (05/10, PR-2) — l'ancien fund_H était du garbage
# (ms comparés à des kilo-secondes) ; le bump invalide tout le cache labels
LABEL_VERSION = "v2"
HORIZONS = (1, 2, 4, 6, 12, 24, 48, 72)  # heures


def snapshot_id(db_path: Path = KDB) -> str:
    """L'identité de l'état des données : un hash du CONTENU 1h
    (symbol|open_time|open|high|low|close|volume) ET du funding_history
    (fix v8, rapport GLM 5.3 №3 : les labels fund_H viennent de
    funding_history — un changement de funding doit invalider le cache des
    labels, l'ancien snapshot ne voyait que les prix)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        h = hashlib.sha256()
        for sym, ots, o, hi, lo, cl, v in con.execute(
                "SELECT symbol, open_time, open, high, low, close, volume "
                "FROM klines WHERE interval='1h' ORDER BY symbol, open_time"):
            h.update(f"{sym}|{ots}|{o}|{hi}|{lo}|{cl}|{v};".encode())
        try:
            for sym, ft, rate in con.execute(
                    "SELECT symbol, funding_time, rate FROM funding_history "
                    "ORDER BY symbol, funding_time"):
                h.update(f"F|{sym}|{ft}|{rate};".encode())
        except sqlite3.Error:
            h.update(b"F|absent;")
        n = h.hexdigest()[:16]
    finally:
        con.close()
    return f"k1h-{n}"


def label_hash(snapshot: str, horizons: tuple[int, ...]) -> str:
    payload = f"{snapshot}|{LABEL_VERSION}|{','.join(map(str, sorted(horizons)))}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _build_symbol(con: sqlite3.Connection, sym: str,
                  horizons: tuple[int, ...], fser: FundingSeries | None
                  ) -> dict[str, np.ndarray]:
    rows = con.execute(
        "SELECT open_time, open, high, low, close FROM klines "
        "WHERE symbol=? AND interval='1h' ORDER BY open_time",
        (sym,)).fetchall()
    if len(rows) < 10:
        raise ValueError(f"{sym} : pas assez de klines ({len(rows)})")
    ts = np.array([r[0] * 10**6 for r in rows], dtype=np.int64)   # ms → ns
    open_ = np.array([r[1] for r in rows], dtype=np.float64)
    high = np.array([r[2] for r in rows], dtype=np.float64)
    low = np.array([r[3] for r in rows], dtype=np.float64)
    close = np.array([r[4] for r in rows], dtype=np.float64)
    n = len(rows)
    out: dict[str, np.ndarray] = {"open_time_ns": ts, "entry": open_}
    hmax = max(horizons)
    # cummax/cummin des fenêtres [i, i+H-1] : via le maximum glissant sur la
    # série RENVERSÉE (numpy sliding window, bon marché même sur 100k barres)
    from numpy.lib.stride_tricks import sliding_window_view
    for H in horizons:
        ret = np.full(n, np.nan)
        hi = np.full(n, np.nan)
        lo = np.full(n, np.nan)
        if n >= H:
            # FIX v8 (2 corrections du rapport GLM 5.3) :
            # 1. le DERNIER event H est valide — i = n-H dispose encore des
            #    H barres i..n-1 (l'ancien code s'arrêtait une ligne trop tôt) ;
            # 2. un label n'est légal que si ses H barres sont CONTIGUËS
            #    (pas de trou horaire traversant le label — un gap ferait
            #    « 6 barres » d'un horizon 6h qui en vaut 8 en temps réel).
            valid_n = n - H + 1
            # ts est en NANOSECONDES : l'écart contigu attendu = (H-1) heures
            gapless = (ts[H - 1:] - ts[:valid_n]) == (H - 1) * 3_600_000_000_000
            ret[:valid_n] = np.where(
                gapless, (close[H - 1:] / open_[:valid_n] - 1.0) * 100.0, np.nan)
            w_h = sliding_window_view(high, H)[:valid_n]   # [i, i+H-1]
            w_l = sliding_window_view(low, H)[:valid_n]
            hi[:valid_n] = np.where(gapless, w_h.max(axis=1) / open_[:valid_n] - 1.0,
                                    np.nan)
            lo[:valid_n] = np.where(gapless, w_l.min(axis=1) / open_[:valid_n] - 1.0,
                                    np.nan)
        out[f"ret_{H}"] = ret
        out[f"hi_{H}"] = hi
        out[f"lo_{H}"] = lo
    # funding cumulé par fenêtre : cumsum des taux as-of (points de %)
    if fser is not None and len(fser.times_ms):
        # FIX v9 (trouvé par le test №5) : times_ms est DÉJÀ en
        # MILLISECONDES (contrat FundingSeries.from_rows) — l'ancien /1e6
        # comparait des ms contre des kilo-secondes : fund_H était du
        # garbage (≈ 0 partout, d'où les « funding net $+0.00 » des wallets)
        fts_ms = fser.times_ms
        cum = np.concatenate(([0.0], np.cumsum(fser.rates_pct)))
        for H in horizons:
            f = np.full(n, np.nan)
            k0 = np.searchsorted(fts_ms, ts / 1e6, side="right")
            k1 = np.searchsorted(fts_ms, ts / 1e6 + H * 3_600_000.0, side="right")
            # FIX v9 (rapport GLM 5.3 №5) : la fenêtre de funding doit être
            # COMPLÈTE — une fenêtre qui dépasse le dernier print connu est
            # INCONNUE (NaN), jamais un partiel tronqué présenté comme
            # complet. La couverture réelle remonte via fund_cov/fund_known.
            # FIX v14 (audit GLM 5.3 №4) : la fenêtre doit être couverte
            # AUX DEUX BOUTS — avant le premier print connu, le funding est
            # INCONNU (l'ancien code donnait 0.0 « connu » aux fenêtres
            # pré-listing-funding : 2025-09 → 2025-10-27 sur univ10)
            known_start = (ts / 1e6 >= fts_ms[0]) | (k1 > k0)
            complete = known_start & (
                (ts / 1e6 + H * 3_600_000.0) <= fts_ms[-1])
            ok = complete & (k1 <= len(cum))
            f[ok] = (cum[np.minimum(k1[ok], len(cum) - 1)]
                     - cum[np.minimum(k0[ok], len(cum) - 1)])
            out[f"fund_{H}"] = f
    else:
        # FIX v6 : PAS de série de funding ≠ funding nul. Le zéro inventé
        # rendait « inconnu » indistinguable de « 0 % » — NaN, et les
        # event_studies rapportent fund_cov ; les masques excluent.
        for H in horizons:
            out[f"fund_{H}"] = np.full(n, np.nan)
    return out


def build_matrix(symbols: list[str], horizons: tuple[int, ...] = HORIZONS,
                 db_path: Path = KDB, use_cache: bool = True,
                 cache_dir: Path | None = None
                 ) -> tuple[str, dict[str, dict[str, np.ndarray]]]:
    """Construit (ou recharge du cache) la matrice de labels. Retourne
    (label_hash, {symbole: {colonne: array}}).

    cache_dir : par défaut le cache partagé du warehouse — les appelants sur
    une DB temporaire (tests, études ad hoc) passent use_cache=False ou un
    cache_dir dédié pour ne jamais polluer le cache de la vraie recherche.
    """
    snap = snapshot_id(db_path)
    lh = label_hash(snap, horizons)
    cdir = Path(cache_dir) if cache_dir else CACHE / lh
    out: dict[str, dict[str, np.ndarray]] = {}
    missing = []
    if use_cache and cdir.exists():
        for sym in symbols:
            f = cdir / f"{sym}.npz"
            if f.exists():
                z = np.load(f)
                out[sym] = {k: z[k] for k in z.files}
        missing = [s for s in symbols if s not in out]
        if not missing:
            return lh, out
    else:
        missing = list(symbols)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        fser_all = funding_series_all(db_path)
        for sym in missing:
            try:
                out[sym] = _build_symbol(con, sym, horizons, fser_all.get(sym))
            except ValueError:
                continue   # symbole sans assez de klines : absent de la matrice
    finally:
        con.close()
    if use_cache:
        cdir.mkdir(parents=True, exist_ok=True)
        meta = {"snapshot_id": snap, "label_hash": lh, "version": LABEL_VERSION,
                "horizons": list(horizons), "symbols": sorted(out)}
        (cdir / "manifest.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        for sym, cols in out.items():
            np.savez_compressed(cdir / f"{sym}.npz", **cols)
    return lh, out


def event_study(cols: dict[str, np.ndarray], mask: np.ndarray, horizon: int,
                side: int = -1, cost_pct: float = 0.28) -> dict:
    """STAGE 1 — l'étude d'événement : un masque de découverte × un horizon →
    les statistiques conditionnelles coûtées (le côté : +1 long, -1 short).
    fund_cov = la part des events dont le funding est CONNU (rapport v6 :
    l'inconnu ne prétend plus être un 0 %)."""
    ret = cols[f"ret_{horizon}"]
    hi = cols[f"hi_{horizon}"]
    lo = cols[f"lo_{horizon}"]
    fund = cols.get(f"fund_{horizon}")
    m = mask & np.isfinite(ret)
    n = int(m.sum())
    if n == 0:
        return {"n": 0}
    if fund is not None:
        fv = fund[m]
        fund_cov = float(np.isfinite(fv).mean())
        fv = np.where(np.isfinite(fv), fv, 0.0)
    else:
        fund_cov = 0.0
        fv = np.zeros(n)
    pos_ret = side * ret[m] + fv * (1 if side == -1 else -1) - cost_pct
    # MAE côté position : short souffre du high, long du low
    mae = (hi[m] if side == -1 else -lo[m])
    q = np.percentile(pos_ret, [10, 50, 90])
    return {"n": n,
            "mean": float(pos_ret.mean()), "median": float(q[1]),
            "p10": float(q[0]), "p90": float(q[2]),
            "wr": float((pos_ret > 0).mean() * 100),
            "mae_mean": float(np.mean(mae)) if len(mae) else None,
            "worst": float(pos_ret.min()), "best": float(pos_ret.max()),
            "fund_cov": fund_cov}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--horizons", default="6,24,72")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    horizons = tuple(int(h) for h in a.horizons.split(","))
    import time as _time
    t0 = _time.time()
    lh, mat = build_matrix(syms, horizons, use_cache=not a.no_cache)
    print(f"label_hash {lh} · {len(mat)}/{len(syms)} symboles · "
          f"horizons {list(horizons)} · {_time.time() - t0:.1f}s")
    demo = next(iter(mat.values()))
    m = np.isfinite(demo[f"ret_{horizons[0]}"])
    print(f"exemple event study ({syms[0]}, {horizons[0]}h, short) : "
          f"{event_study(demo, m, horizons[0], side=-1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
