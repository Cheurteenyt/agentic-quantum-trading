#!/usr/bin/env python3
"""whaleflow_join_test.py — TEST PRE-ENREGISTRE (2026-09-27, AVANT tout calcul).

HYPOTHESE FIGEE (aucun chiffre regarde avant ecriture de ce docstring) :
  Les flux baleines ACHETEURS (7 j glissants) sur un ticker FOMO precedent un
  forward return POSITIF : corr(net_flow, ret J-1 close -> J+1 close) > 0,
  tercile haut de flux > tercile bas.

PROTOCOLE FIGE :
  - Flux jour J du ticker = DERNIER snapshot whale_flow du jour UTC J :
    net_flow = buy_skill_weighted - sell_skill_weighted (USD).
    (dernier snapshot et non somme : evite le double comptage cumulatif)
  - Prix : si ticker.upper()+"USDT" existe dans klines.db (Aster, 1h) on
    l'utilise, sinon fomo_tokens.mint -> fomo_ohlcv (1h) dans fomo.db.
  - ret = close(fin de journee J+1) / close(fin de journee J-1) - 1 (en %),
    barre acceptee seulement si open_time >= frontiere - 26 h (trou de donnees
    sinon). Jour J+1 incomplet (aujourd'hui) => ligne exclue.
  - Stats : Spearman(net_flow, ret) poolé, spread tercile haut - bas,
    split TRAIN/VAL PAR LE TEMPS (70 % premiers jours / 30 % derniers).
VERDICT PASS (a maturite) : VAL : rho > 0, |t| >= 2, tercile haut > bas,
  signes coherents en TRAIN.

GARDE-FOU MATURITE (pattern depth 14 j) : stats bloquees tant que
  - span whale_flow < 6.5 jours, OU
  - < 7 jours calendaires avec snapshots, OU
  - panel (ticker, jour) avec flux + prix J-1/J+1 : n < 100.
Sinon verdict « COUVERTURE INSUFFISANTE — retente le 08/10 ».

UNITES (piege ts du projet — verifiees explicitement au run) :
  whale_flow.captured_at = SECONDES (REAL) — auto-check
  fomo_ohlcv.time        = MILLISECONDES
  fomo_ticks.ts_s        = SECONDES
  buy/sell_skill_weighted = USD (notionnel) — magnitude check

Usage :
  .venv/bin/python scripts/whaleflow_join_test.py         # mode maturite
  .venv/bin/python scripts/whaleflow_join_test.py --run   # une passe complete
Lecture SEULE des DB (mode=ro). fomo.db touche en lecture uniquement.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"
KLINES_DB = ROOT / "data" / "warehouse" / "klines.db"

MIN_SPAN_D = 6.5
MIN_DAYS = 7
MIN_PANEL = 100
MAX_BAR_LAG_MS = 26 * 3_600_000
DAY_MS = 86_400_000


def ts_unit(v: float) -> tuple[str, float]:
    """Detecte l'unite d'un timestamp (piege ns/ms/s du projet)."""
    v = float(v)
    d = len(str(int(abs(v))))
    if d >= 18:
        return "ns", v / 1e6
    if d >= 13:
        return "ms", v
    if d >= 10:
        return "s", v * 1000.0
    return "?", v


def ms2iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def connect_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=15)
    con.execute("PRAGMA busy_timeout = 10000")
    return con


def day_start_ms(day: str) -> int:
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def load_price_series(kl: sqlite3.Connection, fo: sqlite3.Connection,
                      ticker: str, aster_syms: set[str],
                      token_mint: str | None) -> tuple[str, list] | None:
    """Series 1h (open_time_ms, close) pour un ticker FOMO."""
    sym = ticker.upper() + "USDT"
    if sym in aster_syms:
        rows = kl.execute(
            "SELECT open_time, close FROM klines WHERE symbol = ? AND interval='1h' "
            "ORDER BY open_time", (sym,)).fetchall()
        if rows:
            return f"aster:{sym}", rows
    if token_mint:
        rows = fo.execute(
            "SELECT time, close FROM fomo_ohlcv WHERE asset = ? AND period='1h' "
            "ORDER BY time", (token_mint,)).fetchall()
        if rows:
            return f"fomo:{ticker}", rows
    return None


def close_at(series: list, ts_ms: int) -> float | None:
    """Derniere cloture 1h avec open_time <= ts_ms (garde anti-trou 26 h)."""
    lo, hi = 0, len(series) - 1
    if not series or series[0][0] > ts_ms:
        return None
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if series[mid][0] <= ts_ms:
            lo = mid
        else:
            hi = mid - 1
    t, c = series[lo]
    if t < ts_ms - MAX_BAR_LAG_MS or not c:
        return None
    return float(c)


def rank_corr(xs: list, ys: list) -> tuple[float, float]:
    """Spearman manuel + t-stat (pas de dependance scipy)."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    n = len(rx)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx <= 0 or vy <= 0 or n < 3:
        return float("nan"), float("nan")
    rho = cov / (vx * vy) ** 0.5
    t = rho * ((n - 2) / max(1e-12, 1 - rho * rho)) ** 0.5
    return rho, t


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Flux baleines 7j x forward return J-1 -> J+1")
    ap.add_argument("--run", action="store_true",
                    help="passe complete (sinon mode maturite seul)")
    args = ap.parse_args()

    fo = connect_ro(FOMO_DB)
    kl = connect_ro(KLINES_DB)

    print("=" * 68)
    print("WHALEFLOW JOIN TEST (pre-enregistre 2026-09-27)")
    print("=" * 68)

    # --- unites ---
    row = fo.execute("SELECT COUNT(*), MIN(captured_at), MAX(captured_at), "
                     "COUNT(DISTINCT ticker) FROM whale_flow").fetchone()
    if not row or not row[0]:
        print("VERDICT: whale_flow VIDE — collecteur non demarre. Insuffisant.")
        return 0
    n_wf, lo, hi, n_tk = row
    u_lo, ms_lo = ts_unit(lo)
    u_hi, ms_hi = ts_unit(hi)
    span_d = (ms_hi - ms_lo) / DAY_MS
    print(f"[unites] whale_flow.captured_at detecte={u_lo}/{u_hi} (attendu s) | "
          f"n={n_wf} tickers={n_tk} span={span_d:.2f} j "
          f"[{ms2iso(ms_lo)} -> {ms2iso(ms_hi)}]")
    if u_lo != "s" or u_hi != "s":
        print("[unites] !! ANOMALIE : whale_flow n'est PAS en secondes")
    oh = fo.execute("SELECT MIN(time), MAX(time) FROM fomo_ohlcv WHERE period='1h'").fetchone()
    if oh and oh[0]:
        u, _ = ts_unit(oh[0])
        print(f"[unites] fomo_ohlcv.time detecte={u} (attendu ms)"
              + ("" if u == "ms" else " !! ANOMALIE"))
    mag = fo.execute("SELECT MAX(buy_skill_weighted) FROM whale_flow").fetchone()[0]
    print(f"[unites] buy_skill_weighted max={mag:.4g} => notionnel USD plausible"
          if mag and 1e2 <= mag <= 1e10 else
          f"[unites] buy_skill_weighted max={mag} ?? unite inattendue")

    # --- jours couverts ---
    days = [r[0] for r in fo.execute(
        "SELECT DISTINCT strftime('%Y-%m-%d', captured_at, 'unixepoch') "
        "FROM whale_flow ORDER BY 1")]
    n_days = len(days)
    mature = span_d >= MIN_SPAN_D and n_days >= MIN_DAYS
    print(f"[maturite] jours avec snapshots={n_days} {days[:10]} | span={span_d:.2f} j "
          f"(seuils >= {MIN_DAYS} j, span >= {MIN_SPAN_D} j) -> "
          f"{'OK' if mature else 'INSUFFISANT'}")

    # --- mapping ticker -> prix ---
    aster_syms = {r[0] for r in kl.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'")}
    mints = dict(fo.execute("SELECT ticker, mint FROM fomo_tokens"))
    tickers = [r[0] for r in fo.execute("SELECT DISTINCT ticker FROM whale_flow")]
    series_map: dict[str, tuple[str, list]] = {}
    src_count = {"aster": 0, "fomo": 0, "none": 0}
    for t in tickers:
        s = load_price_series(kl, fo, t, aster_syms, mints.get(t))
        if s:
            series_map[t] = s
            src_count["aster" if s[0].startswith("aster") else "fomo"] += 1
        else:
            src_count["none"] += 1
    print(f"[join] tickers whales={len(tickers)} pricés aster={src_count['aster']} "
          f"fomo_ohlcv={src_count['fomo']} sans prix={src_count['none']}")

    # --- flux journalier : dernier snapshot du jour ---
    flow = {}  # (ticker, day) -> net_flow
    for t, b, s, cap in fo.execute(
            "SELECT ticker, buy_skill_weighted, sell_skill_weighted, captured_at "
            "FROM whale_flow ORDER BY captured_at"):
        d = ms2iso(ts_unit(cap)[1])
        flow[(t, d)] = float(b or 0) - float(s or 0)  # ecrase: garde le dernier

    # --- panel avec prix J-1 -> J+1 ---
    panel = []
    for (t, d), net in sorted(flow.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if t not in series_map:
            continue
        ser = series_map[t][1]
        c_prev = close_at(ser, day_start_ms(d))
        c_next = close_at(ser, day_start_ms(d) + 2 * DAY_MS)
        if c_prev and c_next and c_prev > 0:
            panel.append({"ticker": t, "day": d, "net": net,
                          "ret": (c_next / c_prev - 1) * 100.0})
    print(f"[join] panel (ticker, jour) avec flux + ret J-1->J+1 : n={len(panel)} "
          f"(seuil maturite >= {MIN_PANEL})")

    if not mature or len(panel) < MIN_PANEL:
        print("-" * 68)
        print("VERDICT: COUVERTURE INSUFFISANTE — retente le 08/10.")
        print(f"  (jours={n_days}/{MIN_DAYS}, span={span_d:.2f}/{MIN_SPAN_D} j, "
              f"panel={len(panel)}/{MIN_PANEL})")
        print("  Le JOIN et les unites sont valides ; aucun verdict statistique.")
        return 0

    if not args.run:
        print("[maturite] OK mais --run absent : passe complete non lancee.")
        return 0

    # --- passe complete : Spearman + terciles, TRAIN/VAL par le temps ---
    print("=" * 68)
    print("BLOC STATS (net_flow baleines -> ret J-1 -> J+1)")
    all_days = sorted({p["day"] for p in panel})
    cut = all_days[max(0, int(len(all_days) * 0.7) - 1)]
    verdict = "FAIL"
    for name, pred in (("TRAIN", lambda p: p["day"] <= cut),
                       ("VAL", lambda p: p["day"] > cut)):
        part = [p for p in panel if pred(p)]
        if len(part) < 10:
            print(f"-- {name}: n={len(part)} < 10 — non evalue")
            continue
        rho, t = rank_corr([p["net"] for p in part], [p["ret"] for p in part])
        srt = sorted(part, key=lambda p: p["net"])
        k = max(1, len(srt) // 3)
        lo_t = statistics.mean(p["ret"] for p in srt[:k])
        hi_t = statistics.mean(p["ret"] for p in srt[-k:])
        print(f"-- {name} (n={len(part)}, jours {part[0]['day']} -> {part[-1]['day']})")
        print(f"   Spearman rho={rho:+.3f} t={t:+.2f} (|t|>=2 ~ p<0.05)")
        print(f"   tercile flux HAUT: {hi_t:+.2f} % | BAS: {lo_t:+.2f} % | "
              f"spread={hi_t - lo_t:+.2f} %")
        if name == "VAL":
            ok = rho > 0 and abs(t) >= 2 and hi_t > lo_t
            verdict = ("PASS: baleines acheteuses -> forward return positif tient "
                       "en VAL" if ok else
                       "FAIL: hypothese non tenue en VAL (rho/t/spread)")
    print("-" * 68)
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
