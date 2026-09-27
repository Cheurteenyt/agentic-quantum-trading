#!/usr/bin/env python3
"""Étude de la PHASE BONDING (premier gisement) — 2026-09-27.

Thèse user : les ×10-×100 se jouent AVANT la graduation (avant pool_created_at).
Le verdict du 27/09 (reports/fomo-bonding-coverage-2026-09-27.md) a prouvé que
mobula couvre le pré-pool : 1re bougie 1m < pool_created_at (AOC -47 j, AMD -36 min).

Pour chaque token de fomo_tokens (méthode fomo_bonding_test.py : pool_created_at
GT > 1re bougie 1m mobula) on mesure :
  1. chemin PRÉ-POOL : multiple 1re→dernière bougie pré-pool, ATR %, durée,
     drawdown max en cours de phase (close vs running-max).
  2. POST-POOL immédiat : multiple dernière bougie pré-pool → pic 24 h / 72 h.
  3. Signal ex-ante : join bonding_pct (fomo_new_coins) par ticker.
  4. Distribution ×10-×100 : pré-pool et fenêtre totale (survivorship : les
     capturés = les visibles → taux de la population INCONNU, nos chiffres =
     borne vue sur l'échantillon collecté).

UNITÉS (leçon ts_ms) : fomo_ohlcv.time = MILLISECONDES (vérifié par assert),
pool_created_at GT ISO → converti ms. GT free tier : sleep 2.1 s, cooldown 65 s
sur 429. Cache scripts/.gt_pool_cache.json → reruns sans réseau.
Lecture seule data/fomo/fomo.db (WAL). Rapport : reports/fomo-bonding-phase-<date>.md
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fomo" / "fomo.db"
CACHE = ROOT / "scripts" / ".gt_pool_cache.json"
GT = "https://api.geckoterminal.com/api/v2/networks/solana/pools/{}"

QUOTE_TICKERS = frozenset({
    "weth", "cbbtc", "wbtc", "sol", "wsol", "usdc", "usdt", "usds", "jupsol"})


def gt_pool_created_at(pool: str) -> str:
    req = urllib.request.Request(GT.format(pool), headers={"accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)["data"]["attributes"]["pool_created_at"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                print("  GT 429 → cooldown 65s", flush=True)
                time.sleep(65)
                continue
            raise
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3)
    raise RuntimeError("GT indisponible")


def iso_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


def fmt_ms(ms: float | None) -> str:
    if not ms:
        return "n/a"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%m-%d %H:%M")


def dur_h(ms: float) -> str:
    if ms >= 86400_000:
        return f"{ms / 86400_000:.1f} j"
    return f"{ms / 3600_000:.1f} h"


def candles(con: sqlite3.Connection, asset: str, period: str,
            t0: int | None = None, t1: int | None = None) -> list[tuple]:
    q = ("SELECT time, open, high, low, close FROM fomo_ohlcv "
         "WHERE asset=? AND period=?")
    args: list = [asset, period]
    if t0 is not None:
        q += " AND time < ?"
        args.append(t0)
    if t1 is not None:
        q += " AND time >= ? AND time < ?"
        args += [t1, t1 + 72 * 3600_000]
    q += " ORDER BY time"
    return con.execute(q, args).fetchall()


def path_stats(rows: list[tuple]) -> dict:
    """rows 1m (time,o,h,l,c) ordonnés → multiples, ATR%, DD max, durée, continuité.

    La 1re bougie peut porter une open quasi nulle (premier trade de la courbe) :
    le multiple de référence est CLOSE→CLOSE (first_close → last_close),
    l'open-based n'est gardé que comme borne haute artefact.
    """
    fc, o, c = rows[0][4], rows[0][1], rows[-1][4]  # colonnes: time,open,high,low,close
    mult = c / fc if fc else None            # close→close (référence)
    mult_open = c / o if o else None         # artefact 1re open
    atr = statistics.median((h - l) / c for _, _, h, l, c in rows if c)
    peak, dd = rows[0][4], 0.0  # running-max depuis la 1re close (chronologique)
    for *_, cl in rows:
        peak = max(peak, cl)
        dd = min(dd, cl / peak - 1)
    span = rows[-1][0] - rows[0][0]
    cov = len(rows) / (span / 60_000 + 1) if span else 1.0  # % de minutes couvertes
    return {"n": len(rows), "mult": mult, "mult_open": mult_open, "atr": atr,
            "dd": dd, "span": span, "cov": cov, "t0": rows[0][0],
            "t1": rows[-1][0], "first_close": fc, "last_close": c}


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")

    # garde-fou unité ts_ms : les bougies sont bien en millisecondes
    chk = con.execute("SELECT MAX(time) FROM fomo_ohlcv WHERE period='1m'").fetchone()[0]
    assert chk and chk > 1.6e12, f"unité time inattendue: {chk}"

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    tokens = con.execute(
        "SELECT ticker, mint, pool FROM fomo_tokens "
        "WHERE pool IS NOT NULL AND pool != ''").fetchall()
    tokens = [t for t in tokens if t[0].lstrip("$").lower() not in QUOTE_TICKERS]
    print(f"[phase] {len(tokens)} tokens non-quote avec pool", flush=True)

    # bonding_pct (dernier snapshot par ticker, case-insensitive)
    bmap: dict[str, float] = {}
    for tk, bp, _cap in con.execute(
            "SELECT ticker, bonding_pct, captured_at FROM fomo_new_coins "
            "WHERE bonding_pct IS NOT NULL ORDER BY captured_at"):
        bmap[tk.lstrip("$").lower()] = float(bp)

    results = []
    for i, (ticker, mint, pool) in enumerate(sorted(tokens)):
        pool_key = pool[-8:]  # clé de cache courte
        if pool_key not in cache:
            try:
                cache[pool_key] = gt_pool_created_at(pool)
                CACHE.write_text(json.dumps(cache))
                print(f"  GT {ticker}: {cache[pool_key]}", flush=True)
            except Exception as e:
                cache[pool_key] = ""
                print(f"  GT {ticker} ÉCHEC: {e}", flush=True)
            time.sleep(2.1)
        cis = cache[pool_key]
        pool_ms = iso_ms(cis) if cis else None
        first1m = con.execute(
            "SELECT MIN(time) FROM fomo_ohlcv WHERE asset=? AND period='1m'",
            (mint,)).fetchone()[0]
        pre = None
        if pool_ms and first1m and first1m < pool_ms:
            rows = candles(con, mint, "1m", pool_ms)
            if len(rows) < 3:  # 1m trop sparse → fallback 15m
                rows = candles(con, mint, "15m", pool_ms)
                per = "15m"
            else:
                per = "1m"
            if len(rows) >= 3:
                pre = path_stats(rows)
                pre["period"] = per
        post24 = post72 = None
        if pool_ms and pre:
            base = pre["last_close"]
            for lbl, store in (("24h", "p24"), ("72h", "p72")):
                r = con.execute(
                    "SELECT MAX(high) FROM fomo_ohlcv WHERE asset=? AND period='1m' "
                    "AND time>=? AND time<?", (mint, pool_ms,
                                               pool_ms + (24 if lbl == "24h" else 72) * 3600_000)).fetchone()[0]
                if r and base:
                    if lbl == "24h":
                        post24 = r / base
                    else:
                        post72 = r / base
        tot_raw = con.execute(
            "SELECT MAX(high) FROM fomo_ohlcv WHERE asset=? AND period='1m'",
            (mint,)).fetchone()[0]
        # imprimés aberrants (ex. AMBA high=1885$ vs vie ~1e-5) : pic nettoyé =
        # plus haut high ≤ 100 × high médian (robuste aux faux prints)
        med_high = con.execute(
            "SELECT high FROM fomo_ohlcv WHERE asset=? AND period='1m'",
            (mint,)).fetchall()
        highs = sorted(r[0] for r in med_high if r[0])
        mh = statistics.median(highs) if highs else None
        tot_clean, tot_flag = tot_raw, ""
        if tot_raw and mh and tot_raw > 100 * mh:
            tot_clean = max((h for h in highs if h <= 100 * mh), default=tot_raw)
            tot_flag = " [pic nettoyé]"
        tot_mult = tot_clean / pre["first_close"] if (pre and tot_clean) else None
        last_t = con.execute(
            "SELECT MAX(time) FROM fomo_ohlcv WHERE asset=? AND period='1m'",
            (mint,)).fetchone()[0]
        post_trunc = bool(pool_ms and last_t and last_t < pool_ms + 72 * 3600_000)
        results.append({
            "ticker": ticker, "mint": mint, "pool_ms": pool_ms, "pool_iso": cis,
            "first1m": first1m, "pre": pre, "post24": post24, "post72": post72,
            "tot_mult": tot_mult, "post_trunc": post_trunc, "tot_flag": tot_flag,
            "bonding": bmap.get(ticker.lstrip("$").lower()),
        })
        p = pre or {}
        print(f"  {ticker:11s} pool={fmt_ms(pool_ms)} 1re1m={fmt_ms(first1m)} "
              f"pre={('%d x%s' % (p['n'], p['period'])) if p else '-'} "
              f"x_pre={p.get('mult') and round(p['mult'], 1)} "
              f"(open-based artefact x{p.get('mult_open') and round(p['mult_open'], 1)})"
              f"{' [72h tronquée]' if post_trunc else ''}", flush=True)

    con.close()

    prepooled = [r for r in results if r["pre"]]
    pre_m = sorted(r["pre"]["mult"] for r in prepooled if r["pre"]["mult"])
    pre_atr = [r["pre"]["atr"] for r in prepooled]
    pre_dd = [r["pre"]["dd"] for r in prepooled]
    post72 = [r["post72"] for r in prepooled if r["post72"]]
    post24 = [r["post24"] for r in prepooled if r["post24"]]
    tot = [r["tot_mult"] for r in results if r["tot_mult"]]

    def med(xs):
        return statistics.median(xs) if xs else None

    def n10(xs):
        return sum(1 for x in xs if x >= 10)

    def n100(xs):
        return sum(1 for x in xs if x >= 100)

    print("\n[phase] === SYNTHÈSE ===")
    print(f"N exploitables pré-pool : {len(prepooled)}/{len(results)}")
    print(f"× pré-pool médian : {med(pre_m) and round(med(pre_m), 1)} "
          f"(min {min(pre_m):.1f} max {max(pre_m):.1f})" if pre_m else "× pré-pool : n/a")
    print(f"ATR% pré-pool médian : {med(pre_atr) and round(100 * med(pre_atr), 2)}")
    print(f"DD max en phase médian : {med(pre_dd) and round(100 * med(pre_dd), 1)}")
    print(f"× post-graduation 24 h médian : {med(post24) and round(med(post24), 2)}")
    print(f"× post-graduation 72 h médian : {med(post72) and round(med(post72), 2)}")
    cont = sum(1 for r in prepooled if r["post24"] and r["post72"] and r["post72"] > 1.05 * r["post24"])
    print(f"pump qui CONTINUE 24→72 h : {cont}/{sum(1 for r in prepooled if r['post72'])}")
    print(f"×10+ pré-pool : {n10(pre_m)} | ×100+ pré-pool : {n100(pre_m)}")
    print(f"×10+ fenêtre totale : {n10(tot)}/{len(tot)} | ×100+ : {n100(tot)}")
    bb = [(r["ticker"], r["bonding"], r["pre"]["mult"], r["tot_mult"])
          for r in prepooled if r["bonding"]]
    print(f"signal bonding_pct (N={len(bb)}) : {bb}")

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = ROOT / "reports" / f"fomo-bonding-phase-{date}.md"
    with open(out, "w") as f:
        f.write("# Étude phase BONDING — le chemin pré-pool (mobula) du " + date + "\n\n")
        f.write("Thèse : les ×10-×100 se jouent AVANT la graduation. Méthode "
                "fomo_bonding_test.py : pool_created_at (GT) vs MIN(time) 1m mobula. "
                "MC fomo ≠ prix : ici ce sont des PRIX bougies (supply croissante sur "
                "la courbe → les multiples UI fomo sont des MC, les nôtres des prix).\n\n")
        f.write("## Le chemin pré-pool (1re → dernière bougie pré-pool)\n\n")
        f.write("Multiples CLOSE→CLOSE (la 1re bougie porte une open quasi nulle — "
                "premier trade de la courbe — l'open-based est un artefact de borne "
                "haute). Bougies discontinues : DD et chemin = observés aux points "
                "collectés, le creux réel peut être pire (entre les bougies).\n\n")
        f.write("| ticker | pool_created_at | 1re bougie | durée | bougies | couv. | × pré-pool (c→c) | × open-based | ATR% 1m | DD max phase |\n|---|---|---|---|---|---|---|---|---|---|\n")
        for r in sorted(prepooled, key=lambda x: -x["pre"]["mult"]):
            p = r["pre"]
            f.write(f"| {r['ticker']} | {fmt_ms(r['pool_ms'])} | {fmt_ms(p['t0'])} "
                    f"| {dur_h(p['span'])} | {p['n']} ({p['period']}) "
                    f"| {100 * p['cov']:.0f}% | ×{p['mult']:.1f} "
                    f"| ×{p['mult_open'] and round(p['mult_open'], 1)} "
                    f"| {100 * p['atr']:.2f} | {100 * p['dd']:.0f}% |\n")
        f.write("\n## Le pump de graduation existe-t-il APRÈS le pool ?\n\n")
        f.write("| ticker | × pré-pool (c→c) | × 24 h post | × 72 h post | × total (1re close → pic abs) |\n|---|---|---|---|---|\n")
        for r in sorted(prepooled, key=lambda x: -((x["post72"] or 0))):
            fx = lambda v: (f"×{v:.1f}" if v and v >= 0.1 else (f"×{v:.3f}" if v else "n/a"))
            f.write(f"| {r['ticker']}{' [72h tronquée]' if r['post_trunc'] else ''} "
                    f"| {fx(r['pre']['mult'])} "
                    f"| {fx(r['post24'])} "
                    f"| {fx(r['post72'])} "
                    f"| {fx(r['tot_mult'])}{r['tot_flag']} |\n")
        f.write(f"\n## Distribution ×10-×100 (N={len(prepooled)} avec pré-pool "
                f"observable / {len(results)} visibles — survivorship)\n\n")
        f.write(f"- Pré-pool : {n10(pre_m)} ×10+, {n100(pre_m)} ×100+ sur {len(prepooled)}.\n"
                f"- Fenêtre totale : {n10(tot)} ×10+, {n100(tot)} ×100+ sur {len(tot)}.\n"
                f"- ATTENTION : les capturés = les visibles (UI fomo) → biais de "
                f"survie ; le taux de ×10 de la POPULATION totale est inconnu, nos "
                f"chiffres sont la borne observée sur l'échantillon collecté.\n\n")
        f.write("## Signal ex-ante bonding_pct (fomo_new_coins)\n\n")
        f.write("| ticker | bonding_pct | × pré-pool | × total |\n|---|---|---|---|\n")
        for tk, bp, m1, m2 in sorted(bb, key=lambda x: -x[1]):
            f.write(f"| {tk} | {bp:.0f} | ×{m1:.1f} | ×{m2 and round(m2, 1)} |\n")
        f.write(f"\nN={len(bb)} → INDICATIF seulement (join ticker-only, peu de tokens "
                f"bonding ont des bougies mobula : le backfill couvre fomo_tokens).\n")
    print(f"\n[phase] rapport : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
