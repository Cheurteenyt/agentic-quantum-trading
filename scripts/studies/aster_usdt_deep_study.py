#!/usr/bin/env python3
"""ASTERUSDT deep study — étude profonde du marché home de la machine.

One-shot réutilisable :  --section profil|funding|events|machine|all

Lecture SEULEMENT (mode=ro) :
  data/warehouse/klines.db : klines 1m/15m/1h, funding_history, funding_meta,
                             oi_history, oi_history_bulk, liq_events,
                             block_trades, tape_1m, paper_trades, signal_events
  data/warehouse/depth.db  : depth_meta, depth_bins (moteur depth 30 s,
                             locks en salves -> read_retry entre les commits)

Aucune écriture dans les DB de prod ; la sortie va sur stdout.
Conventions : OI bulk = notional USDT x2 (docs/24) -> base = valeur /2.
              depth ts en SECONDES, tout le reste en ms.
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
import time
from datetime import datetime, timezone

BASE = "/run/media/cheurteen/Jeux SSD/trading-agent"
KLINES_DB = f"{BASE}/data/warehouse/klines.db"
DEPTH_DB = f"{BASE}/data/warehouse/depth.db"
SYM = "ASTERUSDT"


def utc(ms_or_s: float, is_s: bool = False) -> str:
    ts = ms_or_s / 1000.0 if not is_s else float(ms_or_s)
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def ro(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)


def read_retry(con: sqlite3.Connection, sql: str, args=(), attempts: int = 40,
               pause: float = 3.0):
    """Exécute en RO en esquivant les salves de locks du depth engine."""
    for i in range(attempts):
        try:
            return con.execute(sql, args).fetchall()
        except sqlite3.OperationalError as e:
            if "locked" not in str(e) and "busy" not in str(e):
                raise
            if i == attempts - 1:
                raise RuntimeError(f"depth.db verrouillée après {attempts} essais: {e}")
            time.sleep(pause)
    return []


# ---------------------------------------------------------------- stats mini

def moments(xs):
    n = len(xs)
    if n < 3:
        return dict(n=n)
    m = sum(xs) / n
    m2 = sum((x - m) ** 2 for x in xs) / n
    m3 = sum((x - m) ** 3 for x in xs) / n
    m4 = sum((x - m) ** 4 for x in xs) / n
    sd = math.sqrt(m2) if m2 > 0 else 0.0
    skew = m3 / sd ** 3 if sd > 0 else 0.0
    kurt = m4 / m2 ** 2 - 3.0 if m2 > 0 else 0.0
    return dict(n=n, mean=m * 1e4, sd=sd * 1e4, skew=skew, kurt=kurt)


def quant(xs, q):
    s = sorted(xs)
    if not s:
        return float("nan")
    i = q * (len(s) - 1)
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def corr(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return float("nan")
    ma, mb = sum(a[:n]) / n, sum(b[:n]) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    va = sum((a[i] - ma) ** 2 for i in range(n)) ** 0.5
    vb = sum((b[i] - mb) ** 2 for i in range(n)) ** 0.5
    return cov / (va * vb) if va > 0 and vb > 0 else float("nan")


# ------------------------------------------------------------------- klines

def load_klines(con, interval):
    cols = [r[1] for r in read_retry(con, "PRAGMA table_info(klines)")]
    want = [c for c in ("open_time", "open", "high", "low", "close", "volume",
                        "quote_volume", "trades", "taker_buy_base",
                        "taker_buy_quote") if c in cols]
    rows = read_retry(con, f"SELECT {','.join(want)} FROM klines "
                           f"WHERE symbol=? AND interval=? ORDER BY open_time",
                      (SYM, interval))
    return [dict(zip(want, r)) for r in rows]


def hole_check(bars, step_s):
    if not bars:
        return "VIDE"
    gaps = []
    prev = bars[0]["open_time"]
    for b in bars[1:]:
        d = b["open_time"] - prev
        if d != step_s * 1000:
            gaps.append((utc(prev), d / 60000.0))
        prev = b["open_time"]
    return gaps


def rets(bars, key="close"):
    out = []
    for a, b in zip(bars, bars[1:]):
        if b[key] > 0 and a[key] > 0:
            out.append(math.log(b[key] / a[key]))
    return out


# ------------------------------------------------------------------ profil

def section_profil():
    con = ro(KLINES_DB)
    print("=" * 78)
    print("SECTION PROFIL — ASTERUSDT (klines + depth + OI)")
    print("=" * 78)

    data = {}
    for iv, step in (("1m", 60), ("15m", 900), ("1h", 3600)):
        bars = load_klines(con, iv)
        data[iv] = bars
        gaps = hole_check(bars, step)
        ngaps = len(gaps) if isinstance(gaps, list) else 0
        span = (bars[-1]["open_time"] - bars[0]["open_time"]) / 86400000.0 if bars else 0
        print(f"\n[{iv}] {len(bars)} bougies  {utc(bars[0]['open_time'])} -> "
              f"{utc(bars[-1]['open_time'])}  ({span:.1f} j)")
        print(f"  trous: {ngaps}" + ("" if not isinstance(gaps, list) else
              f"  premiers: {[(g[0], f'{g[1]:.0f}m') for g in gaps[:5]]}"))

    print("\n--- distributions des rendements (log, x1e4 = bp) ---")
    for iv in ("1m", "15m", "1h"):
        r = rets(data[iv])
        m = moments(r)
        sd = m["sd"] / 1e4
        ann = sd * math.sqrt({"1m": 525600, "15m": 35040, "1h": 8760}[iv]) * 100
        qs = {q: quant(r, q) * 1e4 for q in (0.001, 0.01, 0.05, 0.5, 0.95, 0.99, 0.999)}
        print(f"\n[{iv}] n={m['n']}  sd={m['sd']:.1f}bp  vol_ann~{ann:.0f}%  "
              f"skew={m['skew']:.2f}  kurt_exces={m['kurt']:.1f}")
        print(f"  q0.1%={qs[0.001]:+.0f}bp  q1%={qs[0.01]:+.0f}bp  q5%={qs[0.05]:+.0f}bp  "
              f"med={qs[0.5]:+.2f}bp  q95%={qs[0.95]:+.0f}bp  q99%={qs[0.99]:+.0f}bp  "
              f"q99.9%={qs[0.999]:+.0f}bp")
        print(f"  min={min(r)*1e4:+.0f}bp  max={max(r)*1e4:+.0f}bp  "
              f"ret_norm_q99/sd={qs[0.99]/m['sd']:.2f}")

    print("\n--- régime horaire (15m |ret| moyen par heure UTC + volume) ---")
    by_h = {h: [0.0, 0, 0.0] for h in range(24)}  # sum|ret|, n, sum qvol
    b15 = data["15m"]
    for a, b in zip(b15, b15[1:]):
        if a["close"] > 0 and b["close"] > 0:
            h = datetime.fromtimestamp(a["open_time"] / 1000, tz=timezone.utc).hour
            by_h[h][0] += abs(math.log(b["close"] / a["close"]))
            by_h[h][1] += 1
            by_h[h][2] += b.get("quote_volume", 0.0)
    tot = sum(v[0] for v in by_h.values()) or 1.0
    print("  hUTC  |ret|moy(bp)  vol rel   qvol moyen")
    for h in range(24):
        n = by_h[h][1]
        if n:
            print(f"   {h:02d}   {by_h[h][0]/n*1e4:8.1f}    "
                  f"{by_h[h][0]/tot*100:5.1f}%   {by_h[h][2]/n:12.0f}")

    def hour_of(b):
        return datetime.fromtimestamp(b["open_time"] / 1000, tz=timezone.utc).hour

    day = [abs(math.log(b["close"] / a["close"])) for a, b in zip(b15, b15[1:])
           if a["close"] > 0 and b["close"] > 0 and 6 <= hour_of(a) < 22]
    night = [abs(math.log(b["close"] / a["close"])) for a, b in zip(b15, b15[1:])
             if a["close"] > 0 and b["close"] > 0 and (hour_of(a) >= 22 or hour_of(a) < 6)]
    if day and night:
        md, mn = moments(day), moments(night)
        print(f"\n  jour(06-22UTC): |ret|moy={md['mean']:.1f}bp n={md['n']}   "
              f"nuit(22-06): {mn['mean']:.1f}bp n={mn['n']}  "
              f"ratio nuit/jour={mn['mean']/max(md['mean'],1e-9):.2f}")

    # --- profondeur : spread top-10 (depth_bins échantillonné)
    print("\n--- liquidité carnet (depth_meta/bins, échantillon 1 ts / 20) ---")
    dcon = ro(DEPTH_DB)
    meta = read_retry(dcon, "SELECT ts, mid FROM depth_meta WHERE symbol=? "
                            "ORDER BY ts", (SYM,))
    print(f"  snapshots depth: {len(meta)}  {utc(meta[0][0], True)} -> "
          f"{utc(meta[-1][0], True)}  (pas ~{(meta[-1][0]-meta[0][0])/max(len(meta)-1,1):.1f}s)")
    sample = meta[::20]
    spreads, q10s, hrs = [], [], {}
    bin_steps = []
    for ts, mid in sample:
        rows = read_retry(dcon, "SELECT side, bin_price, qty FROM depth_bins "
                                "WHERE symbol=? AND ts=?", (SYM, ts), attempts=15)
        if len(rows) < 20:
            continue
        bids = sorted((r for r in rows if r[0] == "bid"), key=lambda r: -r[1])
        asks = sorted((r for r in rows if r[0] == "ask"), key=lambda r: r[1])
        if not bids or not asks:
            continue
        step = min([bids[i][1] - bids[i + 1][1] for i in range(len(bids) - 1)
                    if bids[i][1] - bids[i + 1][1] > 0] +
                   [asks[i + 1][1] - asks[i][1] for i in range(len(asks) - 1)
                    if asks[i + 1][1] - asks[i][1] > 0] or [0])
        if step > 0:
            bin_steps.append(step)
        sp_bps = (asks[0][1] - bids[0][1]) / mid * 1e4
        qb = sum(r[2] for r in bids[:10]) * mid
        qa = sum(r[2] for r in asks[:10]) * mid
        spreads.append(sp_bps)
        q10s.append(qb + qa)
        h = datetime.fromtimestamp(ts, tz=timezone.utc).hour
        hrs.setdefault(h // 6, []).append(sp_bps)
    if spreads:
        qs = {q: quant(spreads, q) for q in (0.05, 0.5, 0.95)}
        print(f"  spread binné (bid_best->ask_best): n={len(spreads)}  "
              f"med={qs[0.5]:.2f}bp  q5%={qs[0.05]:.2f}  q95%={qs[0.95]:.2f}")
        labels = {0: "00-06", 1: "06-12", 2: "12-18", 3: "18-24"}
        for k in sorted(hrs):
            v = sorted(hrs[k])
            print(f"    {labels[k]}: med={quant(v,0.5):.2f}bp")
        print(f"  top-10 bid+ask (notional): med={quant(q10s,0.5):,.0f} USDT  "
              f"q95%={quant(q10s,0.95):,.0f}")
        if bin_steps:
            print(f"  pas de bin: med={quant(bin_steps,0.5):g} USDT")

    # --- OI
    print("\n--- OI (bulk = notional x2 -> /2) ---")
    oib = read_retry(con, "SELECT captured_at_ms, open_interest, price FROM "
                          "oi_history_bulk WHERE symbol=? ORDER BY captured_at_ms", (SYM,))
    oih = read_retry(con, "SELECT captured_at_ms, open_interest, price FROM "
                          "oi_history WHERE symbol=? ORDER BY captured_at_ms", (SYM,))
    print(f"  oi_history_bulk: {len(oib)} pts  {utc(oib[0][0])} -> {utc(oib[-1][0])}"
          if oib else "  oi_history_bulk: 0")
    print(f"  oi_history:      {len(oih)} pts  {utc(oih[0][0])} -> {utc(oih[-1][0])}"
          if oih else "  oi_history:      0")
    # ratio bulk/oi_history aux ts proches
    ratios = []
    if oib and oih:
        for ts, v, _ in oib:
            cand = min(oih, key=lambda r: abs(r[0] - ts))
            if abs(cand[0] - ts) < 300_000 and cand[1] > 0:
                ratios.append(v / cand[1])
    if ratios:
        print(f"  ratio bulk/oi_history (ts<5min): med={quant(ratios,0.5):.3f} "
              f"n={len(ratios)}")
    series = oib if len(oib) >= len(oih) else oih
    scale = 0.5 if series is oib else 1.0
    if series:
        oi = [v * scale for _, v, _ in series]
        m1 = data["1m"]
        m1ts = [b["open_time"] for b in m1]
        import bisect

        def close_at(ts_ms):
            i = bisect.bisect_right(m1ts, ts_ms) - 1
            return m1[i]["close"] if i >= 0 else float("nan")

        px = [close_at(ts) for ts, _, _ in series]
        good = [(o, p) for o, p in zip(oi, px) if p == p]
        if len(good) > 5:
            o_g, p_g = zip(*good)
            # corr dOI vs ret : ALIGNE sur les intervalles OI (~15 min bulk),
            # PAS sur des rets 1m (bug d'alignement corrigé)
            doi, rwin = [], []
            for i in range(len(px) - 1):
                if px[i] > 0 and px[i + 1] > 0:
                    doi.append(oi[i + 1] - oi[i])
                    rwin.append(math.log(px[i + 1] / px[i]))
            if series is oih:
                # oi_history = CONTRATS (preuve : bulk/2 = contrats x prix)
                cn, nt = oi, [o * p for o, p in zip(oi, px) if p > 0]
                lbl = f"min={min(cn):,.0f} max={max(cn):,.0f} dern={cn[-1]:,.0f} contrats"
                if nt:
                    lbl += f"  | notional dern={nt[-1]:,.0f} USDT"
            else:
                lbl = f"min={min(oi):,.0f} max={max(oi):,.0f} dern={oi[-1]:,.0f} USDT (base, bulk/2)"
            print(f"  OI: {lbl}")
            print(f"  corr(OI, prix)={corr(list(o_g), list(p_g)):.2f}  n={len(o_g)}  "
                  f"corr(dOI, ret même fenêtre)={corr(doi, rwin):.2f}  n={len(doi)}")

    # --- tape_1m : flow taker
    tape = read_retry(con, "SELECT minute_ts, last_price, n_trades, buy_notional, "
                           "sell_notional FROM tape_1m WHERE symbol=? ORDER BY minute_ts",
                      (SYM,))
    if tape:
        imbs = [(b - s) / (b + s) if (b + s) > 0 else 0.0
                for _, _, _, b, s in tape]
        qv = [b + s for _, _, _, b, s in tape]
        print(f"\n  tape_1m: {len(tape)} min  {utc(tape[0][0])} -> {utc(tape[-1][0])}")
        print(f"    qvol moy={sum(qv)/len(qv):,.0f} USDT/min  "
              f"imbalance med={quant(imbs,0.5):+.3f}  q5%={quant(imbs,0.05):+.3f}  "
              f"q95%={quant(imbs,0.95):+.3f}  |imb|>0.5: "
              f"{sum(1 for x in imbs if abs(x)>0.5)/len(imbs)*100:.1f}%")
    con.close()
    dcon.close()


# ----------------------------------------------------------------- funding

def section_funding():
    con = ro(KLINES_DB)
    print("=" * 78)
    print("SECTION FUNDING — ASTERUSDT (mix 4h/3h, cap ±2%)")
    print("=" * 78)
    meta = read_retry(con, "SELECT * FROM funding_meta WHERE symbol=?", (SYM,))
    cols = [c[1] for c in read_retry(con, "PRAGMA table_info(funding_meta)")]
    if meta:
        print("  funding_meta:", dict(zip(cols, meta[0])))
    rows = read_retry(con, "SELECT funding_time, rate FROM funding_history "
                           "WHERE symbol=? ORDER BY funding_time", (SYM,))
    print(f"\n  {len(rows)} events  {utc(rows[0][0])} -> {utc(rows[-1][0])}  "
          f"({(rows[-1][0]-rows[0][0])/86400000:.1f} j)")
    # normalise : ts s + rate
    ev = [(round(r[0] / 1000), r[1]) for r in rows]
    diffs = [(ev[i + 1][0] - ev[i][0]) / 3600.0 for i in range(len(ev) - 1)]

    def classe(d):
        for h, tol in ((1, 0.15), (2, 0.15), (3, 0.20), (4, 0.20), (8, 0.20)):
            if abs(d - h) <= tol:
                return h
        return None

    print("\n  distribution des intervalles (h):")
    hist = {}
    for d in diffs:
        c = classe(d) or f"autre({d:.2f})"
        hist[c] = hist.get(c, 0) + 1
    for k in sorted(hist, key=str):
        print(f"    {k}h: {hist[k]}")

    # ères : runs de classe
    print("\n  ères (changement d'intervalle):")
    era_start = 0
    cur = classe(diffs[0])
    eras = []
    for i, d in enumerate(diffs[1:], 1):
        c = classe(d)
        if c != cur:
            eras.append((ev[era_start][0], ev[i][0], cur, i - era_start))
            era_start, cur = i, c
    eras.append((ev[era_start][0], ev[-1][0], cur, len(diffs) - era_start))
    for s, e, c, n in eras:
        jours = (e - s) / 86400.0
        print(f"    {utc(s*1000)} -> {utc(e*1000)}  intervalle={c}h  "
              f"{n} events  {jours:.1f} j")

    # heures des events
    hh = {}
    for ts, _ in ev:
        h = datetime.fromtimestamp(ts, tz=timezone.utc).hour
        hh[h] = hh.get(h, 0) + 1
    print("\n  heures UTC des events:", dict(sorted(hh.items())))

    # impact
    print("\n  impact portage :")
    tot = sum(r for _, r in ev)
    jours = (ev[-1][0] - ev[0][0]) / 86400.0
    print(f"    somme cumulée pleine période: {tot*100:+.3f}%  "
          f"({jours:.0f} j)  annualisé {tot/jours*365*100:+.1f}%")
    for s, e, c, n in eras:
        sub = [r for ts, r in ev if s <= ts <= e]
        j = (e - s) / 86400.0
        ann = sum(sub) / j * 365 * 100 if j > 0 else 0
        print(f"    ère {c}h: somme={sum(sub)*100:+.3f}%  mean/event={sum(sub)/max(len(sub),1)*100:+.4f}%"
              f"  annualisé={ann:+.1f}%  max|rate|={max(abs(r) for r in sub)*100:.4f}%")
    cap = read_retry(con, "SELECT fee_cap, fee_floor, rate FROM funding_meta "
                          "WHERE symbol=?", (SYM,))
    if cap and cap[0][0]:
        n_cap = sum(1 for _, r in ev if abs(r) >= min(abs(cap[0][0]), abs(cap[0][1]) or 1))
        print(f"    events au cap (|rate|>= {abs(cap[0][0])*100:.2f}%): {n_cap}")
    con.close()


# ------------------------------------------------------------------ events

def section_events():
    con = ro(KLINES_DB)
    dcon = ro(DEPTH_DB)
    print("=" * 78)
    print("SECTION EVENTS — ASTERUSDT (top mouvements 1h, liq, blocks, murs)")
    print("=" * 78)
    bars = load_klines(con, "1h")
    rr = [(math.log(b["close"] / a["close"]), a["open_time"])
          for a, b in zip(bars, bars[1:]) if a["close"] > 0 and b["close"] > 0]
    top = sorted(rr, key=lambda x: -abs(x[0]))[:20]
    liq = read_retry(con, "SELECT event_time, side, qty, notional FROM liq_events "
                          "WHERE symbol=? ORDER BY event_time", (SYM,))
    blk = read_retry(con, "SELECT ts_ms, is_buyer_maker, notional_usd FROM block_trades "
                          "WHERE symbol=? ORDER BY ts_ms", (SYM,))
    print(f"  liq_events ASTER: {len(liq)}  ({utc(liq[0][0])} -> {utc(liq[-1][0])})"
          if liq else "  liq_events: 0")
    print(f"  block_trades ASTER: {len(blk)}" if blk else "  block_trades: 0")
    print("\n  TOP 20 |ret 1h|  (fenêtre jointure ±1h) :")
    print("  date(UTC)            ret%     liq: n/notion$     blocks: n/notion$")
    for r, t in top:
        w0, w1 = t - 1800_000, t + 3600_000 + 1800_000
        lq2 = [l for l in liq if w0 <= l[0] <= w1]
        n_l = len(lq2)
        nb = sum(1 for x in blk if w0 <= x[0] <= w1)
        nbnot = sum(x[2] for x in blk if w0 <= x[0] <= w1)
        print(f"  {utc(t)}  {r*100:+7.2f}  {n_l:4d}/{sum(x[3] for x in lq2):>12,.0f}"
              f"   {nb:4d}/{nbnot:>12,.0f}")
    tot_l = sum(x[3] for x in liq)
    # convention forceOrder : SELL = long liquidé, BUY = short liquidé
    liq_long = sum(x[3] for x in liq if x[1].upper() == "SELL")
    if liq and tot_l > 0:
        print(f"\n  liq totales: {tot_l:,.0f}$  (longs liquidés {liq_long/tot_l*100:.0f}% / "
              f"shorts {(tot_l-liq_long)/tot_l*100:.0f}%)  "
              f"max event={max(x[3] for x in liq):,.0f}$")
    if blk:
        sells = sum(x[2] for x in blk if x[1] == 1)
        buys = sum(x[2] for x in blk if x[1] == 0)
        print(f"  blocks: achats {buys:,.0f}$ / ventes {sells:,.0f}$  "
              f"max trade={max(x[2] for x in blk):,.0f}$")

    # ---- murs depth_bins
    print("\n  MURS depth_bins (top 15 qty jamais vus, scan par chunks) :")
    meta = read_retry(dcon, "SELECT MIN(ts), MAX(ts) FROM depth_bins WHERE symbol=?",
                      (SYM,))
    t0, t1 = meta[0]
    if t0 is None:
        print("  aucune donnee")
        return
    step = 86400  # chunks d'un jour — top-15 poussé en SQL (24,8M lignes)
    top_walls = []  # (qty, ts, side, bin_price)
    a = t0
    while a <= t1:
        b = min(a + step - 1, t1)
        rows = read_retry(dcon, "SELECT ts, side, bin_price, qty FROM depth_bins "
                                "WHERE symbol=? AND ts BETWEEN ? AND ? "
                                "ORDER BY qty DESC LIMIT 15", (SYM, a, b))
        top_walls.extend(rows)
        top_walls = sorted(top_walls, key=lambda r: -r[3])[:15]
        a = b + 1
    mids = dict(read_retry(dcon, "SELECT ts, mid FROM depth_meta WHERE symbol=?", (SYM,)))
    print("  qty           date(UTC)          side  prix_bin     dist_mid   "
          "vie(>50% pic)")
    for ts, side, bp, q in top_walls[:15]:
        rows = read_retry(dcon, "SELECT ts, qty FROM depth_bins WHERE symbol=? AND "
                                "side=? AND bin_price=? AND ts BETWEEN ? AND ?",
                          (SYM, side, bp, max(t0, ts - 43200), min(t1, ts + 43200)),
                          attempts=15)
        above = [t for t, qq in rows if qq >= 0.5 * q]
        life = (max(above) - min(above)) if above else 0
        mid = mids.get(ts)
        dist = (abs(bp - mid) / mid * 1e4) if mid else float("nan")
        print(f"  {q:12,.0f}  {utc(ts, True)}  {side:>4}  {bp:11.5f}  {dist:7.0f}bp  "
              f"{life/60:.0f} min")
    con.close()
    dcon.close()


# ----------------------------------------------------------------- machine

def section_machine():
    con = ro(KLINES_DB)
    print("=" * 78)
    print("SECTION MACHINE — ASTERUSDT vs l'univers paper_trades")
    print("=" * 78)
    cols = [c[1] for c in read_retry(con, "PRAGMA table_info(paper_trades)")]
    print("  colonnes paper_trades:", cols)
    sel = [c for c in ("signal", "symbol", "horizon_h", "direction", "entry_ts",
                       "entry_price", "exit_ts", "exit_price", "ret_pct",
                       "funding_pct", "status", "fund7", "vol7", "liq24h") if c in cols]
    rows = read_retry(con, f"SELECT {','.join(sel)} FROM paper_trades WHERE symbol=?"
                           " ORDER BY entry_ts", (SYM,))
    print(f"\n  paper_trades ASTERUSDT: {len(rows)}")
    for r in rows:
        print("   ", dict(zip(sel, r)))
    if "vol7" in cols:
        allv = read_retry(con, "SELECT vol7 FROM paper_trades WHERE vol7 IS NOT NULL")
        v = [x[0] for x in allv if x[0] and x[0] > 0]
        ivol = sel.index("vol7") if "vol7" in sel else None
        a = rows[0][ivol] if (rows and ivol is not None and rows[0][ivol] is not None) else None
        if v and a:
            pct = sum(1 for x in v if x < a) / len(v) * 100
            print(f"\n  vol7 ASTER={a:.4f} -> percentile {pct:.0f} sur {len(v)} trades")
    if "fund7" in cols:
        allf = read_retry(con, "SELECT fund7 FROM paper_trades WHERE fund7 IS NOT NULL")
        f = [x[0] for x in allf if x[0] is not None]
        if f:
            print(f"  fund7 univers: med={quant(f,0.5):.4f} p90={quant(f,0.9):.4f} "
                  f"min={min(f):.4f} max={max(f):.4f} (n={len(f)})")
    sig = read_retry(con, "SELECT signal, COUNT(*) FROM signal_events WHERE symbol=? "
                          "GROUP BY signal", (SYM,))
    print("  signal_events ASTER:", sig)
    con.close()


# -------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--section", choices=["profil", "funding", "events", "machine",
                                          "all"], default="all")
    args = ap.parse_args()
    t0 = time.time()
    if args.section in ("profil", "all"):
        section_profil()
    if args.section in ("funding", "all"):
        section_funding()
    if args.section in ("events", "all"):
        section_events()
    if args.section in ("machine", "all"):
        section_machine()
    print(f"\n[fin {args.section} en {time.time()-t0:.0f}s]")


if __name__ == "__main__":
    sys.exit(main())
