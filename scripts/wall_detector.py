#!/usr/bin/env python
"""PROTOTYPE 4,3 j NON-MATURE — détecteur de MURS sur le carnet (depth ~30 s).

PROTOTYPE 4,3 j (NON-MATURE) : fenêtre complète le 06-07/10 — re-tirer tel quel
sur 14 j. Lecture seule de data/warehouse/depth.db (depth_bins + depth_meta,
ts en SECONDES — vérifié, pas de ns ici).

La question institutionnelle : un mur ASK = suppression (prix devrait tomber),
un mur BID = soutien (prix devrait monter). Un mur RETIRÉ avant d'être touché
(PULL) = signature de spoofing — contient-elle de l'information directionnelle ?

Méthode :
  - taille de chaque niveau (notionnel $ = qty x prix) vs baseline locale =
    médiane TRAILING (fenêtre 240 snapshots ~ 2 h, refresh 15 snap ~ 7,5 min,
    strictement passé => zéro lookahead) par (side, distance-au-mid en bps,
    grille 1 bps = grille native du collecteur) ;
  - MUR = notionnel >= 5x (et 10x) baseline ET >= FLOOR_USD ; murs adjacents
    (même snapshot, cols voisines) fusionnés => un mur peut faire plusieurs
    ticks ;
  - cycle de vie (fenêtre de prix ABSOLUE figée au placement) :
      HIT  = le mid atteint la fenêtre du mur (le prix le mange) ;
      PULL = notionnel < max(50% n0, 2x baseline) pendant 2 snapshots SANS
             que le prix ait atteint la fenêtre (retiré avant touch) ;
      SURVIT = censuré (gap data > 120 s, vie > 90 min, fin de données) ;
  - EFFET FORWARD : drift du mid à +5/+15/+30 min (horizons MURAUX) après
    PLACEMENT (t0) et après EVENT (PULL/HIT) ; drift signé par side
    (bid=+, ask=-) => WR = P(mouvement conforme) ;
  - split TRAIN/VAL PAR LE TEMPS 70/30 (par symbole) — n par cellule rapporté
    honnêtement (4,3 j = coupe courte) ;
  - baseline anti-dérive : drift inconditionnel (tous les instants, pas de
    mur) aux mêmes horizons, pour comparer l'ampleur ;
  - persistance : le même niveau de prix (grille tick du symbole) re-placé
    dans les 2 h = acteur persistant vs spoof éphémère ; par tercile de taille.

  .venv/bin/python scripts/wall_detector.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "depth.db"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "ASTERUSDT"]  # couverture complète 4,3 j
BUCKET_BPS = 1.0        # grille native du collecteur (vérifiée : ~1 bps/mid)
MAXD = 150              # ± bps considérés autour du mid
BASE_W = 240            # snapshots de baseline (~2 h)
BASE_STEP = 15          # refresh baseline (~7,5 min)
K_MULTS = (5.0, 10.0)   # multiplicateurs mur
FLOOR_USD = 5_000.0     # plancher absolu du notionnel d'un mur
MIN_BASE_USD = 1_000.0  # baseline minimale pour qu'un bucket soit éligible
PULL_FRAC = 0.5         # mur "parti" si < 50 % du notionnel initial
PULL_BASE_X = 2.0       # ... ou < 2x baseline locale
PULL_SNAPS = 2          # pendant >= 2 snapshots (~60 s)
MIN_EDGE_BPS = 2.0      # bord le plus proche du mid >= 2 bps au placement
                        # (mur institutionnel, pas le spike du best-quote)
GAP_MAX_S = 120         # trou de data au-delà => censure
LIFE_MAX_S = 5400       # 90 min de vie max suivie
HORIZONS = (300, 900, 1800)  # +5/+15/+30 min — horizons MURAUX
H_TOL_S = 90            # tolérance du mid forward (3 snapshots)
TRAIN_FRAC = 0.70       # split train/val PAR LE TEMPS
COOLDOWN = 4            # snapshots avant re-placement du même bucket
FWD_SAMPLE = 30         # pas d'échantillonnage du drift inconditionnel


tick_cluster = 1.0  # (global module, posé par main avant detect_walls)


def build_symbol(con: sqlite3.Connection, sym: str):
    meta = pd.read_sql_query(
        "SELECT ts, mid FROM depth_meta WHERE symbol = ? ORDER BY ts",
        con, params=(sym,))
    ts_u = meta.ts.values.astype(np.int64)
    mid_u = meta.mid.values.astype(np.float64)
    N = len(ts_u)
    K = 2 * MAXD + 1
    mat = {"bid": np.zeros((N, K)), "ask": np.zeros((N, K))}
    clip = tot = 0
    tick_diffs = []
    for chunk in pd.read_sql_query(
            "SELECT ts, side, bin_price, qty FROM depth_bins WHERE symbol = ?",
            con, params=(sym,), chunksize=3_000_000):
        i = np.searchsorted(ts_u, chunk.ts.values)
        m = mid_u[i]
        p = chunk.bin_price.values
        d = (p - m) / m * 1e4
        c = np.rint(d / BUCKET_BPS).astype(np.int64) + MAXD
        ok = (c >= 0) & (c < K) & np.isfinite(m) & (p > 0) & (chunk.qty.values > 0)
        clip += int((~ok & np.isfinite(m)).sum())
        tot += len(chunk)
        if len(tick_diffs) < 200_000:
            sub = np.sort(p[ok][:40_000])
            if len(sub) > 10:
                tick_diffs.append(np.median(np.diff(np.unique(sub))))
        notion = p * chunk.qty.values
        for side in ("bid", "ask"):
            sel = ok & (chunk.side.values == side)
            if not sel.any():
                continue
            idx = i[sel] * K + c[sel]
            mat[side] += np.bincount(idx, weights=notion[sel],
                                     minlength=N * K).reshape(N, K)
    tick = float(np.median(tick_diffs)) if tick_diffs else np.nan
    print(f"[{sym}] snapshots={N} rows={tot} hors-band={clip} ({clip/max(tot,1):.1%}) "
          f"tick=${tick:.4g} couverture={(ts_u[-1]-ts_u[0])/86400:.2f} j")
    return ts_u, mid_u, mat, tick


def trailing_baseline(mat: np.ndarray) -> np.ndarray:
    N, K = mat.shape
    base = np.full((N, K), np.nan)
    for t in range(BASE_W, N, BASE_STEP):
        base[t] = np.median(mat[t - BASE_W:t], axis=0)
    idx = np.arange(N)
    computed = ~np.isnan(base[:, 0])
    last = np.maximum.accumulate(np.where(computed, idx, -1))
    held = base[np.clip(last, 0, N - 1)]
    held[last < 0] = np.nan
    return held


def col_window(p_lo: float, p_hi: float, mid_t: float) -> tuple[int, int]:
    b_lo = int(np.floor((p_lo / mid_t - 1) * 1e4 / BUCKET_BPS + 0.5)) + MAXD
    b_hi = int(np.floor((p_hi / mid_t - 1) * 1e4 / BUCKET_BPS + 0.5)) + MAXD
    return max(b_lo, 0), min(b_hi, 2 * MAXD)


def wall_notion(mat_t: np.ndarray, b_lo: int, b_hi: int) -> float:
    return float(mat_t[b_lo:b_hi + 1].sum())


def detect_walls(sym: str, ts_u, mid_u, mat, k_mult: float):
    N = len(ts_u)
    dt_med = float(np.median(np.diff(ts_u)))
    events = []          # dicts
    open_w: dict[tuple[str, int], dict] = {}
    last_close: dict[tuple[str, int], int] = {}
    for side in ("bid", "ask"):
        m = mat[side]
        base = trailing_baseline(m)
        eligible = np.isfinite(base) & (base >= MIN_BASE_USD)
        mask = eligible & (m >= k_mult * np.where(np.isfinite(base), base, 0)) \
            & (m >= FLOOR_USD)
        prev = np.zeros_like(mask)
        prev[1:] = mask[:-1]
        cont = np.zeros(N, dtype=bool)
        cont[1:] = np.diff(ts_u) <= GAP_MAX_S
        newm = mask & ~prev & cont[:, None]
        rows, cols = np.nonzero(newm)
        by_row: dict[int, list[int]] = {}
        for r, c in zip(rows, cols):
            by_row.setdefault(int(r), []).append(int(c))
        cand = []
        for r, cs in by_row.items():
            cs.sort()
            grp = [cs[0]]
            for c in cs[1:]:
                if c - grp[-1] <= 1:
                    grp.append(c)
                else:
                    cand.append((r, grp[0], grp[-1]))
                    grp = [c]
            cand.append((r, grp[0], grp[-1]))
        # ordre chronologique, dédoublonnage open-wall + cooldown
        cand.sort()
        for t0, cmin, cmax in cand:
            dc_near = (cmin - MAXD) * BUCKET_BPS - BUCKET_BPS / 2 if side == "ask" \
                else abs((cmax - MAXD) * BUCKET_BPS + BUCKET_BPS / 2)
            if dc_near < MIN_EDGE_BPS:
                continue
            key = (side, cmin)
            ow = open_w.get(key)
            if ow is not None:
                continue
            lc = last_close.get(key)
            if lc is not None and t0 - lc < COOLDOWN:
                continue
            dc_lo = (cmin - MAXD) * BUCKET_BPS - BUCKET_BPS / 2
            dc_hi = (cmax - MAXD) * BUCKET_BPS + BUCKET_BPS / 2
            m0 = mid_u[t0]
            p_lo = m0 * (1 + dc_lo / 1e4)
            p_hi = m0 * (1 + dc_hi / 1e4)
            b_lo0, b_hi0 = col_window(p_lo, p_hi, m0)
            n0 = wall_notion(m[t0], b_lo0, b_hi0)
            wall = dict(sym=sym, side=side, t0=t0, cmin=cmin, cmax=cmax,
                        p_lo=p_lo, p_hi=p_hi, n0=n0, base0=float(np.nanmean(
                            base[t0, b_lo0:b_hi0 + 1])))
            open_w[key] = wall
            events.append(wall)
        # --- lifecycle ---
        m_ = mat[side]
        for wall in list(open_w.values()):
            if wall["side"] != side:
                continue
            t = wall["t0"] + 1
            gone = 0
            outcome, t_end = "SURVIT", N - 1
            while t < N:
                if ts_u[t] - ts_u[t - 1] > GAP_MAX_S:
                    outcome, t_end = "SURVIT", t
                    break
                mid_t = mid_u[t]
                # HIT = le prix TRAVERSE la fenêtre (bord lointain) — mission :
                # « le prix le traverse ». Pull = retiré avant traversée.
                touched = (mid_t >= wall["p_hi"]) if side == "ask" \
                    else (mid_t <= wall["p_lo"])
                if touched:
                    outcome, t_end = "HIT", t
                    break
                b_lo, b_hi = col_window(wall["p_lo"], wall["p_hi"], mid_t)
                nt = wall_notion(m_[t], b_lo, b_hi)
                bc = float(np.nanmean(base[t, b_lo:b_hi + 1])) \
                    if np.isfinite(base[t, b_lo:b_hi + 1]).any() else wall["base0"]
                if nt < max(PULL_FRAC * wall["n0"], PULL_BASE_X * bc):
                    gone += 1
                    if gone >= PULL_SNAPS:
                        outcome, t_end = "PULL", t
                        break
                else:
                    gone = 0
                if ts_u[t] - ts_u[wall["t0"]] > LIFE_MAX_S:
                    outcome, t_end = "SURVIT", t
                    break
                t += 1
            wall["outcome"] = outcome
            wall["t_end"] = t_end
            wall["life_s"] = float(ts_u[t_end] - ts_u[wall["t0"]])
            open_w.pop((side, wall["cmin"]))
            last_close[(side, wall["cmin"])] = t_end
        # (les murs jamais fermés dans la boucle ci-dessus restent SURVIT fin de data)
        for wall in open_w.values():
            wall["outcome"] = "SURVIT"
            wall["t_end"] = N - 1
            wall["life_s"] = float(ts_u[-1] - ts_u[wall["t0"]])
        open_w.clear()
    # forward drifts + split + persistance
    t_split = ts_u[0] + TRAIN_FRAC * (ts_u[-1] - ts_u[0])
    for w in events:
        w["split"] = "TRAIN" if ts_u[w["t0"]] <= t_split else "VAL"
        for h in HORIZONS:
            w[f"drift{h//60}"] = forward_drift(ts_u, mid_u, w["t0"], h)
            w[f"edrift{h//60}"] = forward_drift(ts_u, mid_u, w["t_end"], h)
        w["cluster"] = int(round(((w["p_lo"] + w["p_hi"]) / 2) * 100))  # grille cent
        w["t0_s"] = int(ts_u[w["t0"]])
    return events


def forward_drift(ts_u, mid_u, t_ref: int, h: int) -> float:
    target = ts_u[t_ref] + h
    j = int(np.searchsorted(ts_u, target))
    if j >= len(ts_u) or ts_u[j] - target > H_TOL_S:
        return np.nan
    return (mid_u[j] / mid_u[t_ref] - 1) * 1e4


def signed(w, col: str) -> float:
    d = w.get(col)
    if d is None or not np.isfinite(d):
        return np.nan
    return d if w["side"] == "bid" else -d


def rawv(w, col: str) -> float:
    d = w.get(col)
    return float(d) if d is not None and np.isfinite(d) else np.nan


def cell(ws, col: str):
    s = np.array([signed(w, col) for w in ws], dtype=float)
    s = s[np.isfinite(s)]
    if len(s) == 0:
        return dict(n=0, med=np.nan, wr=np.nan, mean=np.nan)
    return dict(n=len(s), med=float(np.median(s)), mean=float(s.mean()),
                wr=float((s > 0).mean()))


def fmt(c) -> str:
    if c["n"] == 0:
        return "n=0"
    return f"n={c['n']} méd={c['med']:+.1f}bp WR={c['wr']:.0%}"


def main() -> int:
    print("=" * 72)
    print("PROTOTYPE 4,3 j NON-MATURE — WALL DETECTOR (re-tir 14 j le 06-07/10)")
    print("=" * 72)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
    all_events: list[dict] = []
    global tick_cluster
    for sym in SYMBOLS:
        ts_u, mid_u, mat, tick = build_symbol(con, sym)
        globals()["tick_cluster"] = tick
        # drift inconditionnel (baseline anti-dérive)
        refs = np.arange(0, len(ts_u) - max(HORIZONS), FWD_SAMPLE)
        reg = (ts_u - ts_u[0]) // 86400
        for h in HORIZONS:
            for tag, rsel in (("HVOL J0-2", refs[reg[refs] <= 2]),
                              ("CALME J3+", refs[reg[refs] >= 3])):
                dr = np.array([forward_drift(ts_u, mid_u, int(t), h) for t in rsel])
                dr = dr[np.isfinite(dr)]
                if len(dr) == 0:
                    continue
                print(f"[{sym}] drift inconditionnel {tag} +{h//60}min : "
                      f"p25={np.percentile(dr,25):+.1f} p50={np.percentile(dr,50):+.1f} "
                      f"p75={np.percentile(dr,75):+.1f} WR(up)={(dr>0).mean():.0%} n={len(dr)}")
        for k in K_MULTS:
            ev = detect_walls(sym, ts_u, mid_u, mat, k)
            print(f"[{sym}] K={k:.0f}x : {len(ev)} murs")
            for w in ev:
                w["k"] = k
            all_events.extend(ev)
    con.close()

    ev5 = [w for w in all_events if w["k"] == 5.0]
    ev10 = [w for w in all_events if w["k"] == 10.0]
    days = None
    print("\n" + "=" * 72)
    print("1) VOLUME & TAILLES (K=5x | K=10x)")
    for sym in SYMBOLS:
        ws5 = [w for w in ev5 if w["sym"] == sym]
        ws10 = [w for w in ev10 if w["sym"] == sym]
        cov = (max(w["t0_s"] for w in ws5) - min(w["t0_s"] for w in ws5)) / 86400 \
            if ws5 else 0
        for tag, ws in (("5x", ws5), ("10x", ws10)):
            if not ws:
                continue
            n0 = np.array([w["n0"] for w in ws])
            per_day = len(ws) / max(cov, 1e-9)
            print(f"[{sym}] K={tag}: n={len(ws)} ({per_day:.0f}/j) | taille$ "
                  f"p50={np.percentile(n0,50):,.0f} p90={np.percentile(n0,90):,.0f} "
                  f"p99={np.percentile(n0,99):,.0f} max={n0.max():,.0f}")
        if ws5:
            tmin = min(w["t0_s"] for w in ws5)
            per_day = {}
            for w in ws5:
                per_day[int((w["t0_s"] - tmin) // 86400)] = \
                    per_day.get(int((w["t0_s"] - tmin) // 86400), 0) + 1
            dist = np.array([abs(int(np.sign(1 if w["side"] == "ask" else -1))
                                 * ((w["cmin"] - MAXD) * BUCKET_BPS)) for w in ws5])
            print(f"[{sym}] murs/jour J0..J{int(max(per_day))}: "
                  + " ".join(f"J{d}={per_day.get(d,0)}" for d in
                             range(int(max(per_day)) + 1))
                  + f" | dist mid bps p25={np.percentile(dist,25):.0f} "
                    f"p50={np.percentile(dist,50):.0f} p75={np.percentile(dist,75):.0f}")

    print("\n2) CYCLE DE VIE : PULL vs HIT vs SURVIT (K=5x)")
    for sym in SYMBOLS:
        ws = [w for w in ev5 if w["sym"] == sym]
        for side in ("bid", "ask"):
            wss = [w for w in ws if w["side"] == side]
            if not wss:
                continue
            n = len(wss)
            nh = sum(w["outcome"] == "HIT" for w in wss)
            npu = sum(w["outcome"] == "PULL" for w in wss)
            nsv = sum(w["outcome"] == "SURVIT" for w in wss)
            lifh = np.median([w["life_s"] for w in wss if w["outcome"] == "HIT"] or [0])
            lifp = np.median([w["life_s"] for w in wss if w["outcome"] == "PULL"] or [0])
            print(f"[{sym}] {side:3s}: n={n} HIT={nh} ({nh/n:.0%}) PULL={npu} "
                  f"({npu/n:.0%}) SURVIT={nsv} ({nsv/n:.0%}) | pull:hit={npu/max(nh,1):.2f} | "
                  f"vie méd HIT={lifh/60:.1f}min PULL={lifp/60:.1f}min")

    print("\n3) EFFET FORWARD après PLACEMENT (drift signé, K=5x, 3 symboles agrégés)"
          " — vs drift inconditionnel")
    print("   (bid = soutien => attendu + ; ask = suppression => attendu -)")
    for h in HORIZONS:
        col = f"drift{h//60}"
        for split in ("TRAIN", "VAL", "ALL"):
            line = f"  +{h//60}min {split:5s}: "
            for side in ("bid", "ask"):
                ws = [w for w in ev5 if w["side"] == side
                      and (split == "ALL" or w["split"] == split)]
                line += f"{side} [{fmt(cell(ws, col))}]  "
            print(line)

    print("\n4) SPOOFING : effet forward après EVENT PULL vs HIT (drift signé, K=5x)")
    for h in HORIZONS:
        col = f"edrift{h//60}"
        for outcome in ("PULL", "HIT"):
            for split in ("TRAIN", "VAL", "ALL"):
                line = f"  +{h//60}min {outcome:4s} {split:5s}: "
                for side in ("bid", "ask"):
                    ws = [w for w in ev5 if w["side"] == side
                          and w["outcome"] == outcome
                          and (split == "ALL" or w["split"] == split)]
                    line += f"{side} [{fmt(cell(ws, col))}]  "
                print(line)

    print("\n4bis) PULL : drift BRUT (les 2 côtés) + per-symbole placement +30min")
    for h in (300, 900, 1800):
        col = f"edrift{h//60}"
        ws = [w for w in ev5 if w["outcome"] == "PULL"]
        v = np.array([rawv(w, col) for w in ws]); v = v[np.isfinite(v)]
        if len(v):
            print(f"  PULL ALL brut +{h//60}min: méd={np.median(v):+.1f}bp "
                  f"WR(down)={(v<0).mean():.0%} n={len(v)}")
    for sym in SYMBOLS:
        ws = [w for w in ev5 if w["sym"] == sym]
        for side in ("bid", "ask"):
            wss = [w for w in ws if w["side"] == side]
            print(f"  [{sym}] placement +30min {side:3s} [{fmt(cell(wss, 'drift30'))}]")

    print("\n5) K=10x (murs stricts) — resumé forward placement +30min")
    for side in ("bid", "ask"):
        for split in ("TRAIN", "VAL"):
            ws = [w for w in ev10 if w["side"] == side and w["split"] == split]
            print(f"  K=10x {side:3s} {split:5s}: [{fmt(cell(ws, 'drift30'))}]")

    print("\n6) PERSISTANCE : re-placement même niveau (±tick) < 2 h (K=5x)")
    for sym in SYMBOLS:
        ws = [w for w in ev5 if w["sym"] == sym]
        ws.sort(key=lambda w: w["t0_s"])
        last_at: dict[tuple[str, int], float] = {}
        re_ok = 0
        sizes = []
        for w in ws:
            key = (w["side"], w["cluster"])
            t0 = w["t0_s"]
            prev_t = last_at.get(key)
            if prev_t is not None and t0 - prev_t <= 7200:
                re_ok += 1
                sizes.append(w["n0"])
            last_at[key] = t0
        if ws:
            n0all = np.array([w["n0"] for w in ws])
            terc = np.percentile(n0all, [33, 67])
            small = sum(1 for w in ws if w["n0"] < terc[0])
            big = sum(1 for w in ws if w["n0"] >= terc[1])
            print(f"[{sym}] murs re-placés <2h: {re_ok}/{len(ws)} ({re_ok/len(ws):.0%}) | "
                  f"n re-placés petit/moyen/gros terciles: {small}/{len(ws)-small-big}/{big}")
    print("\nFIN PROTOTYPE — tout est NON-MATURE (4,3 j), re-tir 06-07/10 sur 14 j.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
