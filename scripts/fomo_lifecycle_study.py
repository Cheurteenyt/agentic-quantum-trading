#!/usr/bin/env python3
"""FOMO lifecycle study — lecture seule de data/fomo/fomo.db.

Pour chaque mint fomo avec >= 500 bougies '1m' OU >= 200 bougies '15m' :
  1. age de la vie couverte (premiere -> derniere bougie, jours)
  2. multiple au pic : MAX(high)/premier close (15m si vie > 5j sinon 1m)
  3. delai jusqu'au pic (heures)
  4. niveau final vs pic : dernier close / MAX(high)
  5. survie : pic <= 24h vs apres, % >= 2x, % finissant < -50% du 1er close

Rapport : reports/fomo-lifecycle-2026-09-27.md
DB ouverte en mode=ro (impossible d'ecrire).
"""

import sqlite3
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "fomo" / "fomo.db"
OUT = ROOT / "reports" / "fomo-lifecycle-2026-09-27.md"

MIN_1M = 500
MIN_15M = 200
LIFE_15M_THRESHOLD_DAYS = 5.0


def fetch():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        counts = dict()
        for asset, period, n in conn.execute(
            "SELECT asset, period, COUNT(*) FROM fomo_ohlcv GROUP BY asset, period"
        ):
            counts.setdefault(asset, {})[period] = n

        tokens = conn.execute(
            "SELECT ticker, mint, pool FROM fomo_tokens WHERE mint IS NOT NULL"
        ).fetchall()

        series = {}
        for asset, period, t, high, close in conn.execute(
            "SELECT asset, period, time, high, close FROM fomo_ohlcv "
            "ORDER BY asset, period, time"
        ):
            series.setdefault((asset, period), []).append((t, high, close))
    finally:
        conn.close()
    return counts, tokens, series


def analyze_one(mint, counts, series):
    n1 = counts.get(mint, {}).get("1m", 0)
    n15 = counts.get(mint, {}).get("15m", 0)
    if n1 < MIN_1M and n15 < MIN_15M:
        return None

    s1 = series.get((mint, "1m"), [])
    s15 = series.get((mint, "15m"), [])
    all_ts = [row[0] for row in s1] + [row[0] for row in s15]
    if not all_ts:
        return None
    t0, t1 = min(all_ts), max(all_ts)
    age_days = (t1 - t0) / 86_400_000.0

    use15 = age_days > LIFE_15M_THRESHOLD_DAYS and n15 >= 50
    rows = s15 if use15 else s1
    if len(rows) < 10:
        rows = s1 if not use15 and len(s1) >= 10 else rows
    if len(rows) < 10:
        return None

    first_t, _, first_close = rows[0]
    if not first_close or first_close <= 0:
        return None
    peak_high = max(h for _, h, _ in rows)
    peak_t = max(rows, key=lambda r: r[1])[0]
    last_close = rows[-1][2]

    multiple = peak_high / first_close
    delay_h = (peak_t - first_t) / 3_600_000.0
    final_vs_peak = last_close / peak_high
    final_vs_first = last_close / first_close
    peaked_24h = delay_h <= 24.0

    return {
        "ticker": None, "mint": mint, "n1m": n1, "n15m": n15,
        "age_days": age_days, "series": "15m" if use15 else "1m",
        "multiple": multiple, "delay_h": delay_h,
        "final_vs_peak": final_vs_peak, "final_vs_first": final_vs_first,
        "peaked_24h": peaked_24h,
    }


def fmt(x, nd=2):
    return f"{x:.{nd}f}"


def main():
    counts, tokens, series = fetch()
    ticker_by_mint = {mint: ticker for ticker, mint, _ in tokens}

    results = []
    seen = set()
    for (mint, _period) in list(series.keys()) + [(a, None) for a in counts]:
        if mint in seen:
            continue
        seen.add(mint)
        r = analyze_one(mint, counts, series)
        if r:
            r["ticker"] = ticker_by_mint.get(mint) or mint[:8]
            results.append(r)

    results.sort(key=lambda r: r["multiple"], reverse=True)
    mults = [r["multiple"] for r in results]
    n = len(results)

    q = statistics.quantiles(mults, n=4) if n >= 4 else [float("nan")] * 3
    med = statistics.median(mults)
    mean = statistics.fmean(mults)
    q1, q3 = q[0], q[2]

    buckets = {
        "0-1.5x": sum(1 for m in mults if m < 1.5),
        "1.5-3x": sum(1 for m in mults if 1.5 <= m < 3),
        "3-10x": sum(1 for m in mults if 3 <= m < 10),
        ">10x": sum(1 for m in mults if m >= 10),
    }
    pct_ge2 = 100 * sum(1 for m in mults if m >= 2) / n
    pct_dead = 100 * sum(1 for r in results if r["final_vs_first"] < 0.5) / n
    med_delay = statistics.median(r["delay_h"] for r in results)

    early = [r["multiple"] for r in results if r["peaked_24h"]]
    late = [r["multiple"] for r in results if not r["peaked_24h"]]
    pct_early = 100 * len(early) / n

    lines = []
    lines.append("# FOMO Lifecycle Study — 2026-09-27")
    lines.append("")
    lines.append(
        f"Source : `data/fomo/fomo.db` (lecture seule, mode=ro). "
        f"Filtre : ≥{MIN_1M} bougies '1m' OU ≥{MIN_15M} bougies '15m'. "
        f"Multiple au pic calculé sur 15m si vie > 5 jours, sinon 1m."
    )
    lines.append("")
    lines.append(f"**{n} tokens analysés.**")
    lines.append("")
    lines.append("## Table par token (triée par multiple au pic décroissant)")
    lines.append("")
    lines.append(
        "| Ticker | Mint | n 1m | n 15m | Vie (j) | Série | Pic (x) | "
        "Délai pic (h) | Fin/Pic | Fin/1er close | Pic ≤24h |"
    )
    lines.append("|---|---|---:|---:|---:|---|---:|---:|---:|---:|---|")
    for r in results:
        lines.append(
            f"| {r['ticker']} | `{r['mint'][:10]}…` | {r['n1m']} | {r['n15m']} "
            f"| {fmt(r['age_days'], 1)} | {r['series']} | **{fmt(r['multiple'])}** "
            f"| {fmt(r['delay_h'], 1)} | {fmt(r['final_vs_peak'], 3)} "
            f"| {fmt(r['final_vs_first'], 3)} | {'oui' if r['peaked_24h'] else 'non'} |"
        )
    lines.append("")
    lines.append("## Synthèse")
    lines.append("")
    lines.append(f"- Multiple au pic : médiane **{fmt(med)}x**, Q1 {fmt(q1)}x, "
                 f"Q3 {fmt(q3)}x, moyenne {fmt(mean)}x (queue droite).")
    lines.append(f"- Distribution : " + ", ".join(
        f"{k} : {v} ({100 * v / n:.0f}%)" for k, v in buckets.items()))
    lines.append(f"- Tokens ≥ 2x : **{pct_ge2:.0f}%** ; "
                 f"fin < -50% du premier close : **{pct_dead:.0f}%**.")
    lines.append(f"- Délai médian au pic : **{fmt(med_delay, 1)} h**.")
    lines.append(f"- Pic atteint ≤ 24h : {pct_early:.0f}% des tokens "
                 f"(médiane pic {fmt(statistics.median(early)) if early else 'n/a'}x) "
                 f"vs après 24h : {100 - pct_early:.0f}% "
                 f"(médiane pic {fmt(statistics.median(late)) if late else 'n/a'}x).")
    lines.append(f"- Niveau final médian vs pic : "
                 f"**{fmt(statistics.median(r['final_vs_peak'] for r in results), 3)}x** "
                 f"(give-back massif après le pic).")
    lines.append("")
    lines.append("## Comparaison à l'ancienne étude (5 tokens, fomo_launch_study.py)")
    lines.append("")
    lines.append("| Métrique | Ancienne étude (n=5) | Cette étude (n=%d) |" % n)
    lines.append("|---|---|---|")
    lines.append(f"| Pic médian | +49% (1.49x) | {fmt(100 * (med - 1))}% ({fmt(med)}x) |")
    lines.append(f"| % qui doublent (≥2x) | 43% | {pct_ge2:.0f}% |")
    lines.append(f"| Moyenne (queue droite) | +578% | {fmt(100 * (mean - 1))}% |")
    lines.append("")
    lines.append(
        "Caveat inchangé : survivorship (les tokens listés sont ceux capturés "
        "par le collecteur fomo, biais vers les launches qui ont eu de l'activité "
        "suffisante pour accumuler ≥500 bougies 1m / ≥200 bougies 15m). "
        "La vie couverte est aussi bornée par la fenêtre de capture du collector."
    )
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ok] {n} tokens -> {OUT}")
    print(f"median={med:.2f}x q1={q1:.2f} q3={q3:.2f} mean={mean:.2f}x")
    print(f">=2x: {pct_ge2:.0f}% | dead<-50%: {pct_dead:.0f}% | "
          f"median delay: {med_delay:.1f}h | dist={buckets}")


if __name__ == "__main__":
    main()
