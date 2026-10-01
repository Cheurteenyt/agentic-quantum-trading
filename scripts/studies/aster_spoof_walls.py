#!/usr/bin/env python
"""T15 — TAXONOMIE DES MURS : réels vs leurres (spoof) — informe le tir
wall_detector du 06-07/10 (PAS de patch du detector ici).

Lecture RO de data/warehouse/depth.db (depth_bins + depth_meta, ts en
SECONDES, alignement bins/meta vérifié 100 %, dt=30 s, ~8,1 j, 15 symboles).

Méthode (suit le pattern T14 : bloc bid 1,46 M$ ASTER à ~630 bps sous le mid,
vie 7-11 min, qty figée, jamais touché) :
  1. par snapshot & side, les bins consécutifs (gap < 2 bps) dont le notionnel
     >= SEED_USD = max(p99 des bins du (symbole, side), 1 k$) forment des BLOCS
     (streaming SQL, lexsort par chunk, runs à cheval portés par carry).
     SEED au p99 et PAS au p90 : sur un carnet profond (BTC/ETH), p90 est sous
     la profondeur de chaque niveau => tout le carnet fusionne en un seul bloc
     de dizaines de G$ ; p99 isole les VRAIS gros niveaux sur tout symbole ;
     fenêtre du bloc = bornes de prix REELLES (min/max des bin_price du run)
     — PAS une reconstruction mid×off : un ordre statique doit garder une
     fenêtre absolue invariante quand le mid bouge ;
  2. BLOC « GROS » = notional du bloc >= p99 des blocs du (symbole, side)
     (mission : « qty > p99 par symbole ») — seuil de NAISSANCE ; le SUIVI
     continue à 0,25x p99 (hystérésis : un mur vivant qui oscille autour du
     seuil p99 ne doit pas être re-cassé toutes les 2 min) ;
  3. TRACKING du bloc à travers ses dérives : un bloc vivant est ré-apparié
     au snapshot suivant s'il chevauche la track EN PRIX ABSOLU (ordre posé à
     prix fixe) OU EN DISTANCE RELATIVE AU MID (bot qui re-place son ordre à
     distance ~constante — la « dérive de bins » du leurre T14 : dist
     642→605 bps glissantes avec qty figée) ;
  4. destin (fenêtre courante, suivie) :
       HIT    = le mid entre dans la fenêtre du bloc (le prix le mange) ;
       PULL   = notional < 50 % du pic pendant 2 snaps, OU disparition
                (non ré-apparié > 90 s) SANS touch — retiré avant touch ;
       SURVIT = censure (trou de data > 120 s, vie > 90 min, fin de data).
  5. features : dist0/dist_med/dist_max au mid (bps, bord le plus proche),
     vie, n0/pic (vitesse d'apparition : 1 = taille pleine dès la naissance),
     taille relative (pic / notional médian du carnet du side ±MAXD),
     dérive propre du bloc (bps), drift du mid +5/+15/+30 min après placement
     (signé par side : bid = + attendu, ask = − attendu) et après destin.

  CLASSES ex-ante (documentées, la table de séparation reste continue) :
       REEL   : dist_med <= 50 bps ET (HIT OU vie >= 30 min)
       LEURRE : jamais touché ET dist_med >= 200 bps ET vie <= 15 min
       AMBIGU : le reste.

Usage :
  .venv/bin/python scripts/studies/aster_spoof_walls.py                # 15 symboles, tout
  .venv/bin/python scripts/studies/aster_spoof_walls.py --symbol ASTERUSDT --days 8
  .venv/bin/python scripts/studies/aster_spoof_walls.py --json reports/aster_spoof_walls_raw.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]  # scripts/studies/ -> racine projet
DB = ROOT / "data" / "warehouse" / "depth.db"

ALL_SYMBOLS = ["BTCUSDT", "ETHUSDT", "ASTERUSDT", "PONSUSDT", "CATEUSDT",
               "MEMEUSDT", "WIFUSDT", "TURBOUSDT", "FARTCOINUSDT", "MOODENGUSDT",
               "BOMEUSDT", "NEIROUSDT", "PNUTUSDT", "DOGSUSDT", "TRUMPUSDT"]

MAXD_BPS = 1000        # demi-largeur d'analyse (le leurre T14 = 630 bps)
GAP_TRACK_S = 90       # non ré-apparié > 90 s => disparition (PULL)
GAP_DATA_S = 120       # trou de data => censure
LIFE_MAX_S = 5400      # 90 min => censure
PULL_FRAC = 0.5        # notional < 50 % du pic
PULL_SNAPS = 2         # pendant 2 snapshots consécutifs
MIN_EDGE_BPS = 2.0     # bord du bloc >= 2 bps du mid à la naissance (anti best-quote)
CONT_FRAC = 0.25       # hystérésis : suivi des blocs vivants >= 25 % du seuil p99
MATCH_TOL_BPS = 8.0    # tolérance d'appariement : gap <= 8 bps en espace absolu
                       # OU relatif (le bot leurre re-place à ~distance constante,
                       # jitter observé 1-3 bps/snap ; un ordre statique voit sa
                       # distance relative glisser avec le mid)
HORIZONS = (300, 900, 1800)
H_TOL_S = 90

# classes ex-ante
REAL_MAX_DIST = 50.0    # bps
REAL_MIN_LIFE = 1800.0  # s
DECOY_MIN_DIST = 200.0  # bps
DECOY_MAX_LIFE = 900.0  # s

DIST_BUCKETS = [(0, 10), (10, 25), (25, 50), (50, 100), (100, 200),
                (200, 500), (500, 1500)]


def forward_drift(ts_u, mid_u, t_ref: int, h: int) -> float:
    target = ts_u[t_ref] + h
    j = int(np.searchsorted(ts_u, target))
    if j >= len(ts_u) or ts_u[j] - target > H_TOL_S:
        return np.nan
    return (mid_u[j] / mid_u[t_ref] - 1) * 1e4


def signed_drift(side: str, raw: float) -> float:
    return raw if side == "bid" else -raw


def seed_thresholds(con, sym: str, t_min: int, t_max: int) -> dict[int, float]:
    """p99 des notionnels de bins sur un échantillon de 6 h (échelle par side)."""
    out = {}
    for side in ("bid", "ask"):
        vals = con.execute(
            f"SELECT qty * bin_price FROM depth_bins WHERE symbol = ? AND side = ? "
            f"AND ts >= ? AND ts <= ? LIMIT 1_200_000",
            (sym, side, t_min, t_min + 21600)).fetchall()
        v = np.array([r[0] for r in vals], dtype=float) if vals else np.array([])
        v = v[np.isfinite(v) & (v > 0)]
        out[0 if side == "bid" else 1] = max(float(np.percentile(v, 99)), 1_000.0) \
            if len(v) >= 10_000 else 1e18
    return out


def run_symbol(con, sym: str, t_min: int) -> tuple[list[dict], dict]:
    meta = np.array(con.execute(
        "SELECT ts, mid FROM depth_meta WHERE symbol = ? AND ts >= ? ORDER BY ts",
        (sym, t_min)).fetchall(), dtype=float)
    if len(meta) == 0:
        return [], {}
    ts_u = meta[:, 0].astype(np.int64)
    mid_u = meta[:, 1]
    N = len(ts_u)
    t_max = int(ts_u[-1])
    t_lo = int(ts_u[0])                      # échantillon = 6 premières h de la fenêtre
    seeds = seed_thresholds(con, sym, t_lo, t_max)
    if any(v >= 1e17 for v in seeds.values()):
        print(f"[{sym}] PAS ASSEZ de données pour les seeds — skip")
        return [], {}

    cur = con.execute(
        "SELECT ts, side, bin_price, qty FROM depth_bins "
        "WHERE symbol = ? AND ts >= ?", (sym, t_min))
    blob_t, blob_s, blob_no, blob_plo, blob_phi = [], [], [], [], []
    blob_olo, blob_ohi = [], []
    book_tot = np.zeros((2, N))
    carry = []            # lignes du run final du chunk précédent
    n_rows = n_aligned = 0
    t0 = time.time()
    while True:
        ch = cur.fetchmany(1_500_000)
        last = len(ch) < 1_500_000
        if not ch and not carry:
            break
        if ch:
            a = np.array(ch, dtype=object)
            del ch
            ts_b = a[:, 0].astype(np.int64)
            sd_b = np.where(a[:, 1] == "bid", 0, 1).astype(np.int8)
            px_b = a[:, 2].astype(np.float64)
            qty_b = a[:, 3].astype(np.float64)
            del a
            n_rows += len(ts_b)
            j = np.searchsorted(ts_u, ts_b)
            n_aligned += int((ts_b == ts_u[np.clip(j, 0, N - 1)]).sum())
            ok = (ts_b == ts_u[np.clip(j, 0, N - 1)])
            mid_b = mid_u[np.clip(j, 0, N - 1)]
            off = (px_b - mid_b) / mid_b * 1e4
            notion = px_b * qty_b
            ok &= np.isfinite(off) & (np.abs(off) <= MAXD_BPS) & (qty_b > 0) & (px_b > 0)
            j = j[ok]; sd_b = sd_b[ok]; off = off[ok]; notion = notion[ok]
            px_b = px_b[ok]
            for s in (0, 1):
                m = sd_b == s
                if m.any():
                    book_tot[s] += np.bincount(j[m], weights=notion[m], minlength=N)
        else:
            j = sd_b = off = notion = px_b = None
        if carry:
            cj, cs, co, cn, cp = (np.array(x) for x in zip(*carry))
            if j is not None:
                j = np.concatenate([cj, j]); sd_b = np.concatenate([cs, sd_b])
                off = np.concatenate([co, off]); notion = np.concatenate([cn, notion])
                px_b = np.concatenate([cp, px_b])
            else:
                j, sd_b, off, notion, px_b = cj, cs, co, cn, cp
            carry = []
        if len(j) == 0 and not last:
            continue
        order = np.lexsort((off, sd_b, j))
        j, sd_b, off, notion, px_b = \
            j[order], sd_b[order], off[order], notion[order], px_b[order]
        newrun = np.empty(len(j), dtype=bool)
        newrun[0] = True
        if len(j) > 1:
            newrun[1:] = (j[1:] != j[:-1]) | (sd_b[1:] != sd_b[:-1]) \
                | (off[1:] - off[:-1] >= 2.0)
        starts = np.nonzero(newrun)[0]
        ends = np.append(starts[1:], len(j))  # exclusif
        for ri in range(len(starts)):
            s0, e0 = int(starts[ri]), int(ends[ri])
            is_final = (e0 < len(j)) or last
            if not is_final:
                carry = list(zip(j[s0:e0], sd_b[s0:e0], off[s0:e0],
                                 notion[s0:e0], px_b[s0:e0]))
                continue
            jj = int(j[s0]); ss = int(sd_b[s0])
            no = float(notion[s0:e0].sum())
            if no < seeds[ss]:
                continue
            plo = float(px_b[s0:e0].min())
            phi = float(px_b[s0:e0].max())
            blob_t.append(jj); blob_s.append(ss); blob_no.append(no)
            blob_plo.append(plo); blob_phi.append(phi)
            blob_olo.append(float(off[s0])); blob_ohi.append(float(off[e0 - 1]))
        if last:
            break
    dt_load = time.time() - t0

    blob_t = np.array(blob_t); blob_s = np.array(blob_s, dtype=np.int8)
    blob_no = np.array(blob_no); blob_plo = np.array(blob_plo)
    blob_phi = np.array(blob_phi)
    blob_olo = np.array(blob_olo); blob_ohi = np.array(blob_ohi)
    bigs = {}
    for s in (0, 1):
        msk = blob_s == s
        tot = blob_no[msk]
        bigs[s] = np.inf
        tag = "p99"
        if len(tot) >= 100:
            # p99 des blocs ; repli 95/90 si < 20 blocs au-dessus (populations
            # dégénérées : mega-blobs persistants sur les carnets profonds)
            for q, name in ((99, "p99"), (95, "p95"), (90, "p90")):
                v = float(np.percentile(tot, q))
                if (tot >= v).sum() >= 20:
                    bigs[s] = v
                    tag = name
                    break
            else:
                bigs[s] = float(np.percentile(tot, 90))
                tag = "p90"
        print(f"[{sym}] side={'bid' if s==0 else 'ask'} seed=${seeds[s]:,.0f} "
              f"blobs={int(msk.sum())} seuil gros bloc={tag}=${bigs[s]:,.0f}")
    print(f"[{sym}] snapshots={N} rows={n_rows} (alignés méta {n_aligned/max(n_rows,1):.1%}) "
          f"blobs={len(blob_t)} chargement={dt_load:.0f}s")
    med_book = {s: float(np.median(book_tot[s][book_tot[s] > 0])) for s in (0, 1)}

    # ---- tracking des gros blocs (naissance p99, suivi 0,25x p99) ----
    birth_mask = (blob_no >= np.where(blob_s == 0, bigs[0], bigs[1]))
    cont_mask = (blob_no >= CONT_FRAC * np.where(blob_s == 0, bigs[0], bigs[1]))
    keep_m = birth_mask | cont_mask
    bt, bs = blob_t[keep_m], blob_s[keep_m]
    bno, bplo, bphi = blob_no[keep_m], blob_plo[keep_m], blob_phi[keep_m]
    bolo, bohi = blob_olo[keep_m], blob_ohi[keep_m]
    is_birth = birth_mask[keep_m]
    del blob_t, blob_s, blob_no, blob_plo, blob_phi, blob_olo, blob_ohi
    tracks: list[dict] = []
    active: dict[int, list[dict]] = {0: [], 1: []}

    def close(tr, t_close, fate, touched_idx=None):
        if tr.get("_closed"):
            return
        tr["_closed"] = True
        tr["fate"] = fate
        tr["t_end_idx"] = t_close if touched_idx is None else touched_idx
        tr["t_end_s"] = int(ts_u[t_close])
        tr["life_s"] = float(ts_u[t_close] - tr["t0_s"])
        tr["dist_med"] = float(np.median(tr["dists"])) if tr["dists"] else tr["dist0"]
        tr["dist_max"] = float(np.max(tr["dists"])) if tr["dists"] else tr["dist0"]
        c0 = 0.5 * (tr["p_lo0"] + tr["p_hi0"])
        cend = 0.5 * (tr["p_lo"] + tr["p_hi"])
        tr["move_bps"] = abs(cend - c0) / mid_u[tr["t0_idx"]] * 1e4
        for h in HORIZONS:
            tr[f"drift{h//60}"] = forward_drift(ts_u, mid_u, tr["t0_idx"], h)
            tr[f"edrift{h//60}"] = forward_drift(ts_u, mid_u, tr["t_end_idx"], h)
        tracks.append(tr)

    nb = len(bt)
    i = 0
    for t in range(N):
        now_s = int(ts_u[t])
        # blobs de ce snapshot (par side)
        snap_blobs = {0: [], 1: []}
        while i < nb and bt[i] == t:
            snap_blobs[int(bs[i])].append((float(bno[i]), float(bplo[i]),
                                           float(bphi[i]), bool(is_birth[i]),
                                           float(bolo[i]), float(bohi[i])))
            i += 1
        for s in (0, 1):
            blobs = snap_blobs[s]
            side = "bid" if s == 0 else "ask"
            # 1) touch test (fenêtre courante suivie)
            still = []
            for tr in active[s]:
                touched = (mid_u[t] >= tr["p_hi"]) if side == "ask" \
                    else (mid_u[t] <= tr["p_lo"])
                if touched:
                    close(tr, t, "HIT", touched_idx=t)
                else:
                    still.append(tr)
            active[s] = still
            # 2) appariement blobs <-> tracks : gap <= MATCH_TOL_BPS en espace
            #    absolu (ordre statique) OU relatif (bot qui re-place)
            pairs = []
            for bi, (no, plo, phi, _, olo, ohi) in enumerate(blobs):
                for ti, tr in enumerate(active[s]):
                    gap_abs = max(plo - tr["p_hi"], tr["p_lo"] - phi, 0.0) \
                        / mid_u[t] * 1e4
                    gap_rel = max(olo - tr["o_hi"], tr["o_lo"] - ohi, 0.0)
                    g = min(gap_abs, gap_rel)
                    if g <= MATCH_TOL_BPS:
                        pairs.append((g, bi, ti))
            pairs.sort(reverse=False)
            used_b, used_t = set(), set()
            for ov, bi, ti in pairs:
                if bi in used_b or ti in used_t:
                    continue
                used_b.add(bi); used_t.add(ti)
                tr = active[s][ti]
                no, plo, phi, _, olo, ohi = blobs[bi]
                dist = ((plo - mid_u[t]) / mid_u[t] * 1e4) if side == "ask" \
                    else ((mid_u[t] - phi) / mid_u[t] * 1e4)
                tr["dists"].append(dist)
                tr["peak"] = max(tr["peak"], no)
                tr["n_low"] = tr["n_low"] + 1 if no < PULL_FRAC * tr["peak"] else 0
                tr["last_s"] = now_s
                tr["p_lo"], tr["p_hi"] = plo, phi
                tr["o_lo"], tr["o_hi"] = olo, ohi
                if tr["n_low"] >= PULL_SNAPS:
                    close(tr, t, "PULL")
            # 3) tracks non appariées : disparition ? (les appariées restent)
            keep = []
            for ti, tr in enumerate(active[s]):
                if tr.get("_closed"):
                    continue
                if ti in used_t:
                    keep.append(tr)
                    continue
                if now_s - tr["last_s"] > GAP_TRACK_S:
                    close(tr, t, "PULL")
                else:
                    keep.append(tr)
            active[s] = keep
            # 4) naissances (seulement les blobs >= p99)
            for bi, (no, plo, phi, birth, olo, ohi) in enumerate(blobs):
                if bi in used_b or not birth:
                    continue
                dist0 = ((plo - mid_u[t]) / mid_u[t] * 1e4) if side == "ask" \
                    else ((mid_u[t] - phi) / mid_u[t] * 1e4)
                if dist0 < MIN_EDGE_BPS:
                    continue
                active[s].append(dict(
                    sym=sym, side=side, t0_idx=t, t0_s=now_s, last_s=now_s,
                    n0=no, peak=no, n_low=0, p_lo0=plo, p_hi0=phi,
                    p_lo=plo, p_hi=phi, o_lo=olo, o_hi=ohi,
                    dist0=dist0, dists=[dist0],
                    rel_size=no / max(med_book[s], 1.0)))
        # censure : trou de data / vie max
        if t > 0 and ts_u[t] - ts_u[t - 1] > GAP_DATA_S:
            for s in (0, 1):
                for tr in active[s]:
                    close(tr, t, "SURVIT")
                active[s] = []
        for s in (0, 1):
            keep = []
            for tr in active[s]:
                if now_s - tr["t0_s"] > LIFE_MAX_S:
                    close(tr, t, "SURVIT")
                else:
                    keep.append(tr)
            active[s] = keep
    for s in (0, 1):
        for tr in active[s]:
            close(tr, N - 1, "SURVIT")
    print(f"[{sym}] tracks gros blocs: {len(tracks)} "
          f"(bid {sum(1 for x in tracks if x['side'] == 'bid')}, "
          f"ask {sum(1 for x in tracks if x['side'] == 'ask')})")
    return tracks, dict(snapshots=N, med_book=med_book, seeds=seeds, bigs=bigs)


def classify(tr: dict) -> str:
    if tr["dist_med"] <= REAL_MAX_DIST and \
            (tr["fate"] == "HIT" or tr["life_s"] >= REAL_MIN_LIFE):
        return "REEL"
    if tr["fate"] != "HIT" and tr["dist_med"] >= DECOY_MIN_DIST \
            and tr["life_s"] <= DECOY_MAX_LIFE:
        return "LEURRE"
    return "AMBIGU"


def pct(x, q):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", action="append", dest="symbols")
    ap.add_argument("--days", type=float, default=None,
                    help="fenêtre glissante depuis la fin (défaut : tout)")
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args()
    symbols = args.symbols or ALL_SYMBOLS

    con = sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")  # collecteurs en écriture continue
    t_end = con.execute("SELECT MAX(ts) FROM depth_meta").fetchone()[0]
    t_min = int(t_end - args.days * 86400) if args.days else 0
    print("=" * 76)
    print(f"T15 SPOOF WALLS — symboles={len(symbols)} "
          f"fenêtre={args.days if args.days else 'tout'} j (ts >= {t_min})")
    print("=" * 76)

    all_tracks: list[dict] = []
    for sym in symbols:
        tracks, _ = run_symbol(con, sym, t_min)
        for tr in tracks:
            tr["cls"] = classify(tr)
        all_tracks.extend(tracks)
    con.close()

    n = len(all_tracks)
    print("\n" + "=" * 76)
    print(f"1) TAXONOMIE (n tracks gros blocs = {n})")
    print("    REEL   = dist_med<=50 bps ET (touché OU vie>=30 min)")
    print("    LEURRE = jamais touché ET dist_med>=200 bps ET vie<=15 min (profil T14)")
    rows = {}
    for cls in ("REEL", "AMBIGU", "LEURRE"):
        ws = [t for t in all_tracks if t["cls"] == cls]
        if not ws:
            continue
        fin = [t for t in ws if np.isfinite(t.get("drift30", np.nan))]
        rows[cls] = dict(
            n=len(ws), pct=len(ws) / n,
            dist_med=pct([t["dist_med"] for t in ws], 50),
            life_med=pct([t["life_s"] for t in ws], 50) / 60,
            size_med=pct([t["peak"] for t in ws], 50),
            n0pk_med=pct([t["n0"] / t["peak"] for t in ws], 50),
            hit=sum(t["fate"] == "HIT" for t in ws) / len(ws),
            pull=sum(t["fate"] == "PULL" for t in ws) / len(ws),
            surv=sum(t["fate"] == "SURVIT" for t in ws) / len(ws),
            rel_med=pct([t["rel_size"] for t in ws], 50),
            move_med=pct([t["move_bps"] for t in ws], 50),
            d30_med=pct([signed_drift(t["side"], t["drift30"]) for t in ws], 50),
            d30_wr=float(np.mean([signed_drift(t["side"], t["drift30"]) > 0
                                  for t in fin])) if fin else np.nan,
            ed30_med=pct([signed_drift(t["side"], t["edrift30"]) for t in ws], 50))
        r = rows[cls]
        print(f"  {cls:6s}: n={r['n']:5d} ({r['pct']:5.1%}) | dist méd={r['dist_med']:6.0f} bp | "
              f"vie méd={r['life_med']:5.1f} min | pic méd=${r['size_med']:,.0f} "
              f"({r['rel_med']:.1f}x carnet) | n0/pic={r['n0pk_med']:.2f} | "
              f"HIT={r['hit']:.0%} PULL={r['pull']:.0%} SURVIT={r['surv']:.0%} | "
              f"move={r['move_med']:.0f} bp | drift30 plac.={r['d30_med']:+.1f} bp "
              f"WR={r['d30_wr']:.0%} | après destin={r['ed30_med']:+.1f} bp")

    print("\n2) DISCRIMINATION : destin & vie par distance au mid (tous symboles)")
    print("   bande bps     n   %HIT  %PULL  %SURV  vie méd (min)  pic méd $  n0/pic  "
          "dist méd")
    for lo, hi in DIST_BUCKETS:
        ws = [t for t in all_tracks if lo <= t["dist_med"] < hi]
        if not ws:
            continue
        f = lambda o: sum(t["fate"] == o for t in ws) / len(ws)
        print(f"   {lo:4.0f}-{hi:4.0f}  {len(ws):5d}  {f('HIT'):5.0%}  {f('PULL'):5.0%}  "
              f"{f('SURVIT'):5.0%}   {pct([t['life_s'] for t in ws], 50)/60:8.1f}  "
              f"{pct([t['peak'] for t in ws], 50):10,.0f}  "
              f"{pct([t['n0']/t['peak'] for t in ws], 50):.2f}  "
              f"{pct([t['dist_med'] for t in ws], 50):7.0f}")

    print("\n3) BANDE DU DETECTOR (2-150 bps) — impact tir 06-07")
    band = [t for t in all_tracks if MIN_EDGE_BPS <= t["dist_med"] <= 150]
    if band:
        fb = lambda o: sum(t["fate"] == o for t in band) / len(band)
        pulls = [t for t in band if t["fate"] == "PULL"]
        decoy_like = [t for t in pulls if t["life_s"] <= DECOY_MAX_LIFE
                      and t["dist_med"] >= 100]
        print(f"   n={len(band)}  HIT={fb('HIT'):.0%} PULL={fb('PULL'):.0%} "
              f"SURVIT={fb('SURVIT'):.0%}")
        print(f"   PULL bande n={len(pulls)} ; profil leurre EN bande "
              f"(vie<=15 min ET dist>=100 bp): {len(decoy_like)} "
              f"({len(decoy_like)/max(len(pulls), 1):.0%} des PULL)")
        for tag, sel in (("PULL tous", pulls),
                         ("PULL leurre-like", decoy_like),
                         ("PULL non-leurre", [t for t in pulls
                                              if t["life_s"] > DECOY_MAX_LIFE
                                              or t["dist_med"] < 100])):
            v = np.array([signed_drift(t["side"], t["edrift30"]) for t in sel])
            v = v[np.isfinite(v)]
            if len(v):
                print(f"   edrift30 {tag:16s}: méd={np.median(v):+.1f} bp "
                      f"WR(sign side)={(v > 0).mean():.0%} n={len(v)}")

    print("\n4) RÈGLE LEURRE PROPOSÉE : dist>=200 bp ET vie<=15 min ET jamais touché")
    rule = [t for t in all_tracks if t["dist_med"] >= DECOY_MIN_DIST
            and t["life_s"] <= DECOY_MAX_LIFE and t["fate"] != "HIT"]
    tp = sum(t["cls"] == "LEURRE" for t in rule)
    fp = sum(t["cls"] == "REEL" for t in rule)
    n_leurres = rows.get("LEURRE", {}).get("n", 0)
    print(f"   captures={len(rule)} dont LEURRE={tp} (précision {tp/max(len(rule), 1):.0%}) ; "
          f"faux REEL capturés={fp} ; rappel LEURRE={tp}/{n_leurres}")
    # contre-test : la règle sur un AUTRE symbole que ASTER (anti coïncidence)
    print("\n   contre-test par symbole (captures règle / tracks, précision vs classe LEURRE):")
    syms_seen = sorted({t["sym"] for t in all_tracks})
    for sym in syms_seen:
        ws = [t for t in all_tracks if t["sym"] == sym]
        cap = [t for t in ws if t["dist_med"] >= DECOY_MIN_DIST
               and t["life_s"] <= DECOY_MAX_LIFE and t["fate"] != "HIT"]
        print(f"   {sym:14s}: tracks={len(ws):4d} captures={len(cap):3d} "
              f"({len(cap)/max(len(ws), 1):.0%}) LEURRE-classe={sum(t['cls']=='LEURRE' for t in ws)}")
    print("\nFIN T15 — étude d'information pour le tir 06-07/10 ; PAS de patch detector.")
    if args.json:
        slim = []
        for t in all_tracks:
            d = {k: v for k, v in t.items()
                 if k not in ("p_lo", "p_hi", "p_lo0", "p_hi0", "dists", "_closed")}
            d["dist_mean"] = float(np.mean(t["dists"])) if t["dists"] else np.nan
            slim.append(d)
        out = dict(generated=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime()), n_tracks=n,
                   classes=rows, tracks=slim)
        Path(args.json).write_text(json.dumps(out, default=float))
        print(f"JSON -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
