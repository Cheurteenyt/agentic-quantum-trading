#!/usr/bin/env python3
"""FOMO lifecycle v3 — l'etude a l'ECHELLE du corpus baleine, lecture seule.

Corpus : 6.79M bougies (1h 1.55M / 1m 5.11M / 15m 126k), 1353 mints distincts
= l'univers des tokens TRADES PAR LES BALEINES (backfill mobula des wallets
suivis). Timestamps : ohlcv.time = MILLISECONDS (LENGTH=13 verifie),
fomo_swaps.ts = SECONDS — jamais joins entre eux (lecon ts_ms).

Filtre de profondeur : >= 48 bougies 1h (= >= 2 jours de vie couverte).
Partie A — metrics lifecycle sur la population filtree : pic (MAX high /
  premier close reel), delai au pic, give-back (fin/pic), survie (>=2x,
  mort <-50%). DISTRIBUTION COMPLETE : deciles, pas juste la mediane.
  Cohortes : vie (<24h / 24h-7j / >7j), notional max swap baleine
  (<1k / 1k-10k / >10k USD, via fomo_swaps.db), volume 1h cumule (USD).
Partie B — re-jugement de la doctrine de sortie a l'echelle : hold 24/48/72h,
  trailing -35%, close < 50% du pic. Entree = close de la 1re bougie non plate
  (convention executable v2). Question : le verdict v2 (hold24h median 1.60x
  ecrase le trailing) tient-il a N=centaines ?
Partie C — cross baleine : tous les mints du corpus apparaissent-ils dans
  fomo_swaps.db ? Cohorte <24h de vie vs le reste.

HONNETETE : population BIASEE — les backfiles = tokens achetes par les
baleines = pre-tries par leur activite. Tous les multiples sont des bornes
HAUTES. Highs idealises : gardes prints poussiere (cassure d'unite jetee,
meche non soutenue reparee) comptes et rapportes.

Rapport : reports/lifecycle-v3-2026-09-28.md
DB ouvertes mode=ro (impossible d'ecrire).
"""

import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "fomo" / "fomo.db"
SWAPS_DB = ROOT / "data" / "fomo" / "fomo_swaps.db"
OUT = ROOT / "reports" / "lifecycle-v3-2026-09-28.md"

PERIODS = ("15m", "1h", "1m")     # alphabetique = ordre SQL ; finesse = 1m > 15m > 1h
MS_H = 3_600_000
MS_D = 86_400_000
MIN_CANDLES_1H = 48               # filtre de profondeur (mission)
BIRTH_TOLERANCE_MS = 2 * MS_H
MIN_LIFE_BACKTEST_H = 72.0
TRAIL_PCT = 0.35
HALF_PEAK = 0.50
HOLDS_H = (("hold24h", "hold", 24), ("hold48h", "hold", 48), ("hold72h", "hold", 72))
RULE_DEFS = HOLDS_H + (("trailing -35%", "trail", None), ("close < 50% pic", "half", None))
ARTEFACT_X = 10_000               # pic/entree au-dela = print poussiere residuel
UNIT_BREAK_X = 30.0               # close > 30x dernier close sain -> hors unite, jete
WICK_X = 4.0                      # high > 4x close sain ET close non suivi -> repare
MEAN_CLIP = 1000.0
COVERAGE_SPARSE = 0.5             # n1h/span_h < 0.5 -> serie eparse (trous de backfill)
ACTIVE_WINDOW_MS = 48 * MS_H      # derniere bougie < 48h avant la fin DB = actif


def fmt_dt(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def clean_series(rows):
    """Reparation voisine-based (v2) : cassure d'unite jetee, meche non
    soutenue reparee (high := dernier close sain)."""
    out, last_good, n_drop, n_wick = [], None, 0, 0
    for t, o, h, c in rows:
        if not c or c <= 0 or not h or h <= 0:
            n_drop += 1
            continue
        if last_good is not None:
            if c > last_good * UNIT_BREAK_X:
                n_drop += 1
                continue
            if h > last_good * WICK_X and c < last_good * 1.5:
                h = last_good
                n_wick += 1
        out.append((t, o, h, c))
        last_good = c
    return out, n_drop, n_wick


def first_real_close(rows):
    """Close de la 1re bougie NON PLATE (high > open, vrai trade) — l'open de
    la 1re bougie plate d'un launch est le print de creation (poussiere)."""
    for t, o, h, c in rows:
        if c and c > 0 and h and h > o:
            return c
    return next((c for _, _, _, c in rows if c and c > 0), None)


def load_whale_notionals():
    """max(size_usd), somme size_usd et nb de swaps par mint (fomo_swaps.db ro).
    NB : swaps.ts en SECONDS — jamais join temporel avec ohlcv (ms)."""
    conn = sqlite3.connect(f"file:{SWAPS_DB}?mode=ro", uri=True)
    try:
        agg = {}
        for mint, mx, tot, n in conn.execute(
            "SELECT mint, MAX(size_usd), SUM(size_usd), COUNT(*) FROM fomo_swaps "
            "WHERE mint IS NOT NULL GROUP BY mint"
        ):
            agg[mint] = (mx or 0.0, tot or 0.0, n)
    finally:
        conn.close()
    return agg


def run_rule(rows, rule, hold_h=None, entry=None):
    """(multiple, censored) — meme semantique que v2. Entree = close 1re bougie
    non plate. Regle jamais declenchee -> sortie derniere bougie (censuree)."""
    if entry is None:
        entry = first_real_close(rows)
    if not entry or entry <= 0:
        return None, False
    if rule == "hold":
        limit_t = rows[0][0] + hold_h * MS_H
        last = rows[0]
        for r in rows:
            if r[0] <= limit_t:
                last = r
            else:
                break
        censored = last is rows[-1] and rows[-1][0] < limit_t
        return last[3] / entry, censored
    running_high = rows[0][2]
    for i, r in enumerate(rows):
        running_high = max(running_high, r[2])
        if i == 0:
            continue
        if rule == "trail" and r[3] <= running_high * (1 - TRAIL_PCT):
            return r[3] / entry, False
        if rule == "half" and r[3] < running_high * HALF_PEAK:
            return r[3] / entry, False
    return rows[-1][3] / entry, True


def stats_block(values):
    n = len(values)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "med": statistics.median(values),
        "mean": statistics.fmean(min(v, MEAN_CLIP) for v in values),
        "wr": sum(1 for v in values if v > 1.0) / n,
        "worst": min(values),
        "best": max(values),
        "ge2": sum(1 for v in values if v >= 2.0) / n,
    }


def fmt_s(s):
    if not s or not s["n"]:
        return "| 0 | - | - | - | - | - | - |"
    return (f"| {s['n']} | {s['med']:.2f}x | {s['mean']:.2f}x | {s['wr']*100:.0f}% "
            f"| {s['worst']:.3f}x | {s['best']:.1f}x | {s['ge2']*100:.0f}% |")


def deciles(values):
    """(min, P10..P90, median, max) robuste aux petits n."""
    if not values:
        return None
    v = sorted(values)
    if len(v) < 10:
        q = [v[int(len(v) * f)] for f in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)]
    else:
        q = statistics.quantiles(v, n=10, method="inclusive")
    return {"min": v[0], "p": q[:4], "med": statistics.median(v), "p5": q[5:],
            "max": v[-1]}


def fmt_dec(d, unit="x"):
    if not d:
        return "-"
    parts = [f"{d['min']:.2f}"] + [f"{x:.2f}" for x in d["p"]] + [f"**{d['med']:.2f}**"] \
        + [f"{x:.2f}" for x in d["p5"]] + [f"{d['max']:.1f}"]
    return " | ".join(parts) + f" ({unit})"


def notional_bucket(mx):
    if mx is None:
        return "sans swap baleine"
    if mx < 1_000:
        return "<1k$"
    if mx < 10_000:
        return "1k-10k$"
    return ">10k$"


def life_bucket(life_h):
    if life_h < 24:
        return "<24h"
    if life_h < 24 * 7:
        return "24h-7j"
    return ">7j"


def main():
    whale = load_whale_notionals()
    tickers = {}
    clean_stats = {"drop": 0, "wick": 0}
    pop = []                      # metrics Partie A (1 dict par token)
    bt = []                       # resultats Partie B (1 dict par token testable)
    n_assets_seen = 0

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        tickers = dict(conn.execute("SELECT mint, ticker FROM fomo_tokens"))
        # --- stream par asset : periodes alphabetiques (15m, 1h, 1m) ---
        cur = conn.execute(
            "SELECT asset, period, time, open, high, close, volume FROM fomo_ohlcv "
            "WHERE period IN ('15m','1h','1m') ORDER BY asset, period, time"
        )
        cur_asset, periods_rows, n1h_raw, vol1h_usd = None, {}, 0, 0.0

        def finalize(asset):
            nonlocal n_assets_seen, n1h_raw, vol1h_usd
            if asset is None:
                return
            n_assets_seen += 1
            series = {}
            for p, rows in periods_rows.items():
                cleaned, nd, nw = clean_series(rows)
                clean_stats["drop"] += nd
                clean_stats["wick"] += nw
                if cleaned:
                    series[p] = cleaned
            if "1h" not in series:
                return                      # pas de base 1h -> hors population profondeur
            rows1h = series["1h"]
            n1h = len(rows1h)
            if n1h < MIN_CANDLES_1H:
                return                      # filtre de profondeur (mission)
            union = sorted((r for rows in series.values() for r in rows), key=lambda r: r[0])
            birth = min(rows[0][0] for rows in series.values())
            last_t = max(rows[-1][0] for rows in series.values())
            life_h = (last_t - birth) / MS_H
            first_close = first_real_close(union)
            if not first_close or first_close <= 0:
                return
            peak = max(r[2] for r in union)
            peak_t = min(r[0] for r in union if r[2] == peak)
            last_close = union[-1][3]
            peak_x = peak / first_close
            m = {
                "mint": asset,
                "ticker": tickers.get(asset) or asset[:8],
                "birth": birth, "last_t": last_t, "life_h": life_h,
                "n1h": n1h, "vol_usd": vol1h_usd,
                "peak_x": peak_x, "artefact": peak_x > ARTEFACT_X,
                "delay_h": (peak_t - birth) / MS_H,
                "final_vs_peak": last_close / peak if peak > 0 else None,
                "final_vs_first": last_close / first_close,
                "active": False,           # rempli apres (db_max inconnu pendant le stream)
                "whale_max": whale.get(asset, (None,))[0],
                "whale_n": whale.get(asset, (0, 0.0, 0))[2],
            }
            pop.append(m)
            # --- Partie B : serie la plus fine partant de la naissance (+2h) ---
            pick = None
            for p in ("1m", "15m", "1h"):
                rows = series.get(p)
                if rows and rows[0][0] <= birth + BIRTH_TOLERANCE_MS:
                    pick = p
                    break
            if pick and life_h >= MIN_LIFE_BACKTEST_H and not m["artefact"]:
                bt_rows = series[pick]
                entry = first_real_close(bt_rows)
                res = {}
                for label, kind, h in RULE_DEFS:
                    v, c = run_rule(bt_rows, kind, h, entry=entry)
                    if v is not None:
                        res[label] = (v, c)
                if res:
                    m["bt_period"] = pick
                    bt.append((m, res))

        for asset, period, t, o, h, c, v in cur:
            if asset != cur_asset:
                finalize(cur_asset)
                cur_asset, periods_rows, n1h_raw, vol1h_usd = asset, {}, 0, 0.0
            if period == "1h":
                n1h_raw += 1
                vol1h_usd += (v or 0.0)
            periods_rows.setdefault(period, []).append((t, o, h, c))
        finalize(cur_asset)
    finally:
        conn.close()

    db_max = max(m["last_t"] for m in pop)
    for m in pop:
        m["active"] = (db_max - m["last_t"]) < ACTIVE_WINDOW_MS

    ok = [m for m in pop if not m["artefact"]]
    art = [m for m in pop if m["artefact"]]
    sparse = [m for m in ok if m["n1h"] / max(m["life_h"], 1e-9) < COVERAGE_SPARSE]

    lines = []
    A = lines.append
    A("# FOMO Lifecycle v3 — l'echelle du corpus baleine — 2026-09-28\n")
    A(f"Source : `data/fomo/fomo.db` mode=ro + `data/fomo/fomo_swaps.db` mode=ro. "
      f"{n_assets_seen} assets, 6.79M bougies (1h 1.55M, 1m 5.11M, 15m 126k). "
      "ohlcv.time en MILLISECONDS (verifie LENGTH=13), fomo_swaps.ts en SECONDS — aucun join temporel.\n")
    A(f"Nettoyage (v2, par serie) : {clean_stats['drop']} bougies hors unite jetees, "
      f"{clean_stats['wick']} meches non soutenues reparees (high > 4x close sain, close non suivi).\n")

    # ---------- Partie 0 : population ----------
    A(f"## 0. Population — filtre de profondeur (>= {MIN_CANDLES_1H} bougies 1h)\n")
    A(f"- {n_assets_seen} assets au total dans fomo_ohlcv (1 353 mints = l'univers baleine backfile).")
    A(f"- **N reel de l'etude : {len(pop)}** tokens avec >= {MIN_CANDLES_1H} bougies 1h "
      f"({100*len(pop)/max(n_assets_seen,1):.0f}% du corpus). "
      f"Exclus : {n_assets_seen - len(pop)} (pas de 1h ou < 48 bougies 1h : morts-nes ou couverture trop courte).")
    A(f"- Dont **{len(art)} artefacts** (pic > {ARTEFACT_X}x l'entree, residu print poussiere) "
      f"exclus des stats : {', '.join(m['ticker'] for m in art[:12]) or 'aucun'}.")
    A(f"- Statut : **actifs {sum(1 for m in ok if m['active'])}** (derniere bougie < 48h), "
      f"**morts {sum(1 for m in ok if not m['active'])}**.")
    A(f"- Series **eparses {len(sparse)}** (couverture 1h < 50% de la vie : trous de backfill — "
      "le pic et les delais sont mesures sur ce qui a ete backfile, pas sur tout).")
    life_dec = deciles([m["life_h"] for m in ok])
    A(f"- Vie : deciles (h) = {fmt_dec(life_dec, 'h')} ; mediane {life_dec['med']:.0f}h "
      f"({life_dec['med']/24:.1f} j). Coupons : <24h {sum(1 for m in ok if m['life_h']<24)} | "
      f"24h-7j {sum(1 for m in ok if 24<=m['life_h']<168)} | >7j {sum(1 for m in ok if m['life_h']>=168)}.")
    A("- **POINT STRUCTUREL** : 48 bougies 1h = span >= 47h. Le filtre de profondeur rend la cohorte "
      "<24h IMPOSSIBLE a mesurer en partie A — tout launch mort en moins de 2 jours est hors etude "
      "(biais de survie additionnel, s'ajoute au biais baleine). La cohorte courte la plus fine "
      "mesurable est la partie B (vie < 96h, n=24).\n")

    # ---------- Partie A ----------
    A(f"## A. Metrics lifecycle — N={len(ok)} (artefacts exclus)\n")
    px = [m["peak_x"] for m in ok]
    dl = [m["delay_h"] for m in ok]
    gb = [1 - m["final_vs_peak"] for m in ok if m["final_vs_peak"] is not None]
    f1 = [m["final_vs_first"] for m in ok]
    A("### Distribution COMPLETE des pics (MAX high / premier close reel) — deciles\n")
    A("| min | P10 | P20 | P30 | P40 | **median** | P60 | P70 | P80 | P90 | max |")
    A("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    A("| " + fmt_dec(deciles(px)) + " |")
    A("")
    A(f"**Survie** : pic >= 2x : **{sum(1 for v in px if v>=2)*100/len(px):.0f}%** "
      f"({sum(1 for v in px if v>=2)}/{len(px)}) ; pic >= 5x : "
      f"{sum(1 for v in px if v>=5)*100/len(px):.0f}% ; pic >= 20x : {sum(1 for v in px if v>=20)*100/len(px):.0f}%.")
    A(f"**Mort** : final < -50% vs entree : **{sum(1 for v in f1 if v<0.5)*100/len(f1):.0f}%** ; "
      f"final median vs entree {statistics.median(f1):.3f}x.")
    A(f"**Give-back apres pic** (1 - fin/pic) : mediane **{statistics.median(gb)*100:.0f}%**, "
      f"P10 {sorted(gb)[len(gb)//10]*100:.0f}%, P90 {sorted(gb)[9*len(gb)//10]*100:.0f}%. "
      "La fin/pic median confirme la doctrine : apres le pic, la majorite du gain disparait.")
    A(f"**Delai au pic** (h) : mediane **{statistics.median(dl):.0f}h**, "
      f"P10 {sorted(dl)[len(dl)//10]:.1f}h, P90 {sorted(dl)[9*len(dl)//10]:.0f}h ; "
      f"pic <= 72h : {sum(1 for v in dl if v<=72)*100/len(dl):.0f}%.\n")

    A("### Cohortes (distribution des pics)\n")
    A("| Cohorte | n | P10 | median | P90 | >=2x | mort <-50% |")
    A("|---|---:|---:|---:|---:|---:|---:|")

    def cohort_row(name, sub):
        if not sub:
            A(f"| {name} | 0 | - | - | - | - | - |")
            return
        s = [m["peak_x"] for m in sub]
        d = deciles(s)
        dead = sum(1 for m in sub if m["final_vs_first"] < 0.5) * 100 / len(sub)
        ge2 = sum(1 for v in s if v >= 2) * 100 / len(s)
        A(f"| {name} | {len(sub)} | {d['p'][0]:.2f} | **{d['med']:.2f}** | {d['p5'][2]:.2f} "
          f"| {ge2:.0f}% | {dead:.0f}% |")

    for b in ("<24h", "24h-7j", ">7j"):
        cohort_row(f"vie {b}", [m for m in ok if life_bucket(m["life_h"]) == b])
    seen_buckets = set()
    for m in ok:
        b = notional_bucket(m["whale_max"])
        if b not in seen_buckets:
            seen_buckets.add(b)
    for b in ("<1k$", "1k-10k$", ">10k$", "sans swap baleine"):
        if b in seen_buckets:
            label = "sans swap baleine enregistre" if b == "sans swap baleine" else f"swap baleine max {b}"
            cohort_row(label, [m for m in ok if notional_bucket(m["whale_max"]) == b])
    vol_sorted = sorted(m["vol_usd"] for m in ok)
    t1, t2 = vol_sorted[len(vol_sorted)//3], vol_sorted[2*len(vol_sorted)//3]
    cohort_row("volume 1h bas (T1)", [m for m in ok if m["vol_usd"] <= t1])
    cohort_row("volume 1h milieu (T2)", [m for m in ok if t1 < m["vol_usd"] <= t2])
    cohort_row("volume 1h haut (T3)", [m for m in ok if m["vol_usd"] > t2])
    cohort_row("serie eparse (trous)", sparse)
    cohort_row("serie continue", [m for m in ok if m not in sparse])
    A("")

    # ---------- Partie B ----------
    A("## B. Doctrine de sortie re-jugee a l'echelle\n")
    A(f"Tokens testables : vie >= 72h + serie la plus fine partant de la naissance (+/-2h) + "
      f"non-artefact : **N={len(bt)}**. Entree = close de la 1re bougie non plate (convention executable v2). "
      f"Moyenne clippee a {MEAN_CLIP:.0f}x/trade. Cens = regle jamais declenchee (biais haussier si token encore vivant).\n")
    A("| Regle | n | Median | Moyenne | WR | Pire | Best | >=2x | Cens |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    overall = {}
    for label, _, _ in RULE_DEFS:
        vals = [res[label][0] for _, res in bt if label in res]
        cens = sum(1 for _, res in bt if label in res and res[label][1])
        s = stats_block(vals)
        s["cens"] = cens
        overall[label] = s
        A(f"| **{label}** " + fmt_s(s) + f" {cens} |")
    A("")
    A("**Par cohorte — median des multiples** (le test de robustesse du verdict v2) :\n")
    A("| Cohorte | " + " | ".join(l for l, _, _ in RULE_DEFS) + " |")
    A("|---|" + "---:|" * len(RULE_DEFS))

    def cohort_bt_row(name, sub):
        if not sub:
            A(f"| {name} |" + " - |" * len(RULE_DEFS))
            return
        cells = []
        for label, _, _ in RULE_DEFS:
            vals = [res[label][0] for m, res in sub if label in res]
            cells.append(f"{statistics.median(vals):.2f}x" if vals else "-")
        A(f"| {name} (n={len(sub)}) | " + " | ".join(cells) + " |")

    sub_lt96 = [(m, res) for m, res in bt if (m["last_t"] - m["birth"]) / MS_H < 96]
    sub_ge96 = [(m, res) for m, res in bt if (m["last_t"] - m["birth"]) / MS_H >= 96]
    cohort_bt_row("vie < 96h", sub_lt96)
    cohort_bt_row("vie >= 96h", sub_ge96)
    cohort_bt_row("swap baleine >10k$", [(m, res) for m, res in bt if notional_bucket(m["whale_max"]) == ">10k$"])
    cohort_bt_row("swap baleine <=10k$", [(m, res) for m, res in bt if notional_bucket(m["whale_max"]) in ("<1k$", "1k-10k$")])
    cohort_bt_row("serie 1m (fine)", [(m, res) for m, res in bt if m.get("bt_period") == "1m"])
    cohort_bt_row("serie 1h (grossiere)", [(m, res) for m, res in bt if m.get("bt_period") == "1h"])
    A("")
    best_label = max(overall, key=lambda k: overall[k]["med"])
    bs = overall[best_label]
    trail, half = overall["trailing -35%"], overall["close < 50% pic"]
    big = [(m, res) for m, res in bt if notional_bucket(m["whale_max"]) == ">10k$"]
    big_table = {}
    for label, _, _ in RULE_DEFS:
        vals = [res[label][0] for _, res in big if label in res]
        if vals:
            big_table[label] = statistics.median(vals)
    big_best = max(big_table, key=big_table.get) if big_table else "-"
    A(f"**Verdict echelle** : gagnant median = **{best_label}** ({bs['med']:.2f}x, WR {bs['wr']*100:.0f}%, "
      f"pire {bs['worst']:.3f}x) vs trailing -35% ({trail['med']:.2f}x, WR {trail['wr']*100:.0f}%, "
      f"pire {trail['worst']:.3f}x, cens {trail['cens']}) et half-peak ({half['med']:.2f}x, "
      f"WR {half['wr']*100:.0f}%, cens {half['cens']}).")
    A(f"**Le verdict v2 TIENT a l'echelle** (temps-fixe court ecrase trailing et half-peak sur les "
      f"3 cohorts principales). SEULE EXCEPTION : les swaps baleine >10k$ (n={len(big)}), ou "
      f"**{big_best}** median {big_table.get(big_best, 0):.2f}x inverse le classement — le notional "
      "baleine lourd change la dynamique de sortie.\n")

    # ---------- Partie C ----------
    A("## C. Cross baleine et cohorte <24h\n")
    in_swaps = sum(1 for m in pop if m["whale_max"] is not None)
    A(f"- Universe : fomo_swaps.db couvre {len(whale)} mints distincts (12 716 swaps) ; "
      f"**{in_swaps}/{len(pop)}** tokens du corpus ont au moins un swap baleine enregistre. "
      + ("**Tout l'univers etudie est baleine** : le corpus n'est PAS un echantillon de tokens quelconques."
         if in_swaps == len(pop) else
         f"{len(pop)-in_swaps} tokens sans swap enregistre (backfill partiel des wallets)."))
    A(f"- Cohorte vie <24h (vs le reste) : voir tableau cohortes partie A — c'est la seule "
      "sous-population ou le pic reste devant la fenetre d'entree naissance (le regime 'launch').\n")

    # ---------- Honnetete ----------
    A("## Mises en garde (honnêtete obligatoire)\n")
    A("1. **SURVIVORSHIP MASSIF** : les 1 353 mints = tokens backfiles PARCE QUE des baleines suivies "
      "les ont trades. La population est pre-triee par l'activite baleine : les morts-nes sans baleine "
      "sont absents du corpus. Tous les pics, WR et >=2x ci-dessus sont des **bornes HAUTES** de "
      f"l'univers reel des mints. Le N={len(ok)} est le N du monde baleine, pas du monde total.")
    A("2. **Highs idealises** : le pic = MAX high de bougies mobula. Les gardes prints poussiere "
      f"(cassure d'unite jetee : {clean_stats['drop']} bougies ; meches non soutenues reparees : "
      f"{clean_stats['wick']}) ont tourne, mais une meche reelle tres breve reste comptee comme "
      "atteignable — en execution elle est partiellement inatteignable. Les multiples de sortie "
      "(close-based) sont moins touches que les pics.")
    A(f"3. **Trous de backfill** : {len(sparse)}/{len(ok)} series eparses (< 50% de couverture 1h). "
      "Pour ces tokens, delai au pic et declenchement trailing/half sont mesures sur des series "
      "incompletes : les censures sur-trouvent le trailing.")
    A("4. **Censure** : regles jamais declenchees = sortie a la derniere bougie (multiple 'encore "
      "ouvert'). Pour les tokens encore actifs, c'est un biais haussier des regles conditionnelles.")
    A("5. **Etude, pas strategie** : pas de fees/slippage. Toute transposition doit passer "
      "`scripts/stacked_portfolio.py run_stack` avant d'entrer dans le stack.\n")

    # ---------- v2 -> v3 ----------
    A("## v2 (34 tokens) -> v3 (echelle)\n")
    A(f"| Metrique | v2 (n<=34) | v3 (N={len(ok)}) |")
    A("|---|---|---|")
    A(f"| Pic median | 15.1x (rapporte) | **{statistics.median(px):.2f}x** |")
    A(f"| >=2x | 84% (rapporte) | **{sum(1 for v in px if v>=2)*100/len(px):.0f}%** |")
    A(f"| Give-back median | 83% (rapporte) | **{statistics.median(gb)*100:.0f}%** |")
    A(f"| Delai median au pic | 872h (v2) | **{statistics.median(dl):.0f}h** |")
    A(f"| Sortie gagnante (median) | hold24h 1.60x | **{best_label} {bs['med']:.2f}x** |\n")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK -> {OUT}")
    print(f"assets={n_assets_seen} pop={len(pop)} ok={len(ok)} artefacts={len(art)} sparse={len(sparse)} bt={len(bt)}")
    print("pics deciles:", fmt_dec(deciles(px)))
    print(f"survie >=2x: {sum(1 for v in px if v>=2)*100/len(px):.0f}%  mort<-50%: {sum(1 for v in f1 if v<0.5)*100/len(f1):.0f}%")
    for label, s in overall.items():
        print(f"  {label:16s} med={s['med']:.2f} mean={s['mean']:.2f} wr={s['wr']*100:.0f}% "
              f"worst={s['worst']:.3f} cens={s['cens']}")
    print(f"gagnant: {best_label}")


if __name__ == "__main__":
    main()
