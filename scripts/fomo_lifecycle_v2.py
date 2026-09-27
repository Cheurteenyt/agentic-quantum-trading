#!/usr/bin/env python3
"""FOMO lifecycle study v2 — corpus profond (backfill mobula), lecture seule.

Corpus : 386k bougies, 34 tokens. 1m remonte a fev 2025, 15m a nov 2024,
1h a avr 2024. Timestamps en MILLISECONDS (verifie : LENGTH(time)=13).

Partie A — metriques lifecycle sur tokens avec >= 14 jours de donnees (1m/15m/1h) :
  pic, delai au pic, give-back (dernier close / pic), survie.
  Cohortes : ne avant 2026-06-01 vs apres (recence = regime actuel).

Partie B — backtest de sortie. Entree = 1re bougie disponible (naissance capturee).
  Serie choisie : la plus fine dont la 1re bougie <= naissance_proxy + 2h
  (1m > 15m > 1h) — pour les vieux tokens, seul le 1h part de la naissance.
  Regles : (a) hold 48h, (b) hold 72h, (c) trailing -35% depuis le plus haut,
  (d) 1re bougie close < 50% du pic, (e) hold 24h (controle).
  Metriques : multiple median/moyen, WR, pire trade, best, %>=2x, censure.

NB : MC != prix n'est PAS un probleme ici (bougies mobula = prix).
Rapport : reports/fomo-lifecycle-v2-2026-09-27.md
DB ouverte mode=ro (impossible d'ecrire).
"""

import sqlite3
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "fomo" / "fomo.db"
OUT = ROOT / "reports" / "fomo-lifecycle-v2-2026-09-27.md"

PERIODS = ("1m", "15m", "1h")
MS_H = 3_600_000
MS_D = 86_400_000
JUNE_2026 = 1_780_272_000_000          # 2026-06-01 00:00 UTC
MIN_LIFE_DAYS = 14.0                   # partie A
MIN_LIFE_BACKTEST_H = 72.0             # partie B : horloge complete pour hold 72h
BIRTH_TOLERANCE_MS = 2 * MS_H          # 1re bougie "a la naissance" si <= +2h
TRAIL_PCT = 0.35
HALF_PEAK = 0.50
HOLDS_H = {"hold24h": 24, "hold48h": 48, "hold72h": 72}


def fmt_dt(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def load():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        tickers = dict(conn.execute("SELECT mint, ticker FROM fomo_tokens"))
        series = {}
        for asset, period, t, o, h, c in conn.execute(
            "SELECT asset, period, time, open, high, close FROM fomo_ohlcv "
            "WHERE period IN ('1m','15m','1h') ORDER BY asset, period, time"
        ):
            series.setdefault((asset, period), []).append((t, o, h, c))
    finally:
        conn.close()
    return tickers, series


def build_tokens(series, tickers):
    """Un record par asset : naissance proxy, vie, series disponibles (nettoyees)."""
    tokens = {}
    clean_stats = {"drop": 0, "wick": 0}
    for (asset, period), rows in series.items():
        cleaned, nd, nw = clean_series(rows)
        clean_stats["drop"] += nd
        clean_stats["wick"] += nw
        tok = tokens.setdefault(asset, {"mint": asset, "series": {}})
        tok["series"][period] = cleaned
    for asset, tok in tokens.items():
        births = {p: rows[0][0] for p, rows in tok["series"].items()}
        tok["birth"] = min(births.values())
        last_t = max(rows[-1][0] for rows in tok["series"].values())
        tok["last_t"] = last_t
        tok["life_days"] = (last_t - tok["birth"]) / MS_D
        tok["ticker"] = tickers.get(asset) or asset[:8]
        # plus fine serie partant de la naissance (+/- tolerance)
        pick = None
        for p in PERIODS:                      # 1m d'abord
            rows = tok["series"].get(p)
            if rows and rows[0][0] <= tok["birth"] + BIRTH_TOLERANCE_MS:
                pick = p
                break
        tok["bt_period"] = pick
        tok["bt_rows"] = tok["series"].get(pick) if pick else None
        # cohort
        tok["cohort"] = "avant juin 2026" if tok["birth"] < JUNE_2026 else "apres juin 2026"
    db_max = max(t["last_t"] for t in tokens.values())
    for tok in tokens.values():
        tok["active"] = (db_max - tok["last_t"]) < 48 * MS_H
        birth_row = min((r for p in PERIODS for r in tok["series"].get(p, [])), key=lambda r: r[0])
        tok["birth_open"] = birth_row[1] or birth_row[3]
        tok["type"] = "launch" if (tok["birth_open"] or 0) < MAJOR_OPEN_THRESHOLD else "majeur"
    return tokens, clean_stats


def first_real_close(rows):
    """Close de la 1re bougie NON PLATE (high > low, vrai trade) — l'open/close de la
    1re bougie plate d'un launch est le print de creation (poussiere, inachetable)."""
    for t, o, h, c in rows:
        if c and c > 0 and h and h > o:
            return c
    return next((c for _, _, _, c in rows if c and c > 0), None)


MAJOR_OPEN_THRESHOLD = 0.01   # open >= 0.01$ a la naissance = majeur/lisse, sinon launch (bonding curve)
UNIT_BREAK_X = 30.0           # close > 30x dernier close sain -> bougie hors unite, jetee
WICK_X = 4.0                  # high > 4x dernier close sain ET close non soutenu -> high repare
MEAN_CLIP = 1000.0            # moyenne clippee par trade (bornage des prints poussiere)


def clean_series(rows):
    """Reparation voisine-based (dans la meme serie) :
    - cassure d'unite (cas AMBA 1m : bougies a ~1566$ vs 0.0012$) -> jetees ;
    - mèche erratique non soutenue (cas WETH 1h : high 13210 vs ~3100) -> high := dernier close sain.
    Retourne (rows_propres, n_drop, n_wick)."""
    out, last_good, n_drop, n_wick = [], None, 0, 0
    for r in rows:
        t, o, h, c = r
        if not c or c <= 0 or not h or h <= 0:
            n_drop += 1
            continue
        if last_good is not None:
            if c > last_good * UNIT_BREAK_X:            # bougie hors unite
                n_drop += 1
                continue
            if h > last_good * WICK_X and c < last_good * 1.5:
                h = last_good                            # mèche non soutenue
                n_wick += 1
        out.append((t, o, h, c))
        last_good = c
    return out, n_drop, n_wick


def lifecycle_metrics(tok):
    """Pic / delai / give-back sur l'UNION des series nettoyees, triees par temps."""
    all_rows = sorted((r for p in PERIODS for r in tok["series"].get(p, [])), key=lambda r: r[0])
    first_close = first_real_close(all_rows)
    if not first_close or first_close <= 0:
        return None
    peak = max(r[2] for r in all_rows)
    peak_t = min(r[0] for r in all_rows if r[2] == peak)   # 1re occurrence du pic
    last_close = all_rows[-1][3]
    return {
        "peak_x": peak / first_close,
        "delay_h": (peak_t - tok["birth"]) / MS_H,
        "final_vs_peak": last_close / peak,
        "final_vs_first": last_close / first_close,
        "artefact": (peak / first_close) > 10_000,
    }


def run_rule(rows, rule, hold_h=None, entry=None):
    """Retourne (multiple, censored). Entree par defaut = close de la 1re bougie
    non plate (exécutable) ; l'open de la 1re bougie d'un launch = print de
    creation a ~1e-12..1e-6$, inachetable en pratique (voir mise en garde)."""
    if entry is None:
        entry = first_real_close(rows)
    if not entry or entry <= 0:
        return None, False
    n = len(rows)
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
    return rows[-1][3] / entry, True          # jamais declenche -> censure


def stats_block(values):
    n = len(values)
    if not n:
        return {"n": 0}
    ge2 = sum(1 for v in values if v >= 2.0)
    return {
        "n": n,
        "med": statistics.median(values),
        "mean": statistics.fmean(min(v, MEAN_CLIP) for v in values),
        "wr": sum(1 for v in values if v > 1.0) / n,
        "worst": min(values),
        "best": max(values),
        "ge2": ge2 / n,
    }


def fmt_s(s):
    if not s or not s["n"]:
        return "| - | - | - | - | - | - | - | - |"
    return (f"| {s['n']} | {s['med']:.2f}x | {s['mean']:.2f}x | {s['wr']*100:.0f}% "
            f"| {s['worst']:.3f}x | {s['best']:.1f}x | {s['ge2']*100:.0f}% |")


def main():
    tickers, series = load()
    tokens, clean_stats = build_tokens(series, tickers)
    db_max = max(t["last_t"] for t in tokens.values())

    lines = []
    lines.append("# FOMO Lifecycle v2 — corpus profond — 2026-09-27\n")
    lines.append("Source : `data/fomo/fomo.db` mode=ro (386k bougies, 34 tokens, backfill mobula). "
                 "Timestamps verifies en millisecondes. NB : bougies mobula = prix, MC != prix non applicable.\n")
    lines.append(f"Nettoyage donnees (par serie, reference = dernier close sain) : "
                 f"{clean_stats['drop']} bougies hors unite jetees (cassure d'unite, cas AMBA 1m ~1566$ vs 0.0012$), "
                 f"{clean_stats['wick']} meches non soutenues reparees (high > 4x close sain et close non suivi, "
                 f"cas WETH 1h high=13210 vs ~3100).\n")

    # ---------- Partie A ----------
    full = [t for t in tokens.values() if t["life_days"] >= MIN_LIFE_DAYS]
    lines.append(f"## Partie A — lifecycle, tokens avec >= {MIN_LIFE_DAYS:.0f} jours : {len(full)}/{len(tokens)}\n")
    lines.append("| Ticker | Type | Cohorte | Naissance | Vie (j) | Pic (x) | Delai pic (h) | Fin/Pic | Fin/1er | Statut |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---|")
    met_by_token = {}
    for tok in sorted(full, key=lambda t: t["birth"]):
        m = lifecycle_metrics(tok)
        if not m:
            continue
        met_by_token[tok["mint"]] = m
        statut = "actif" if tok["active"] else "mort"
        flag = " (artefact print poussiere)" if m["artefact"] else ""
        short = "avant 06/26" if tok["cohort"].startswith("avant") else "apres 06/26"
        lines.append(
            f"| {tok['ticker']} | {tok['type']} | {short} | "
            f"{fmt_dt(tok['birth'])[:10]} | {tok['life_days']:.1f} | **{m['peak_x']:.2f}x**{flag} | "
            f"{m['delay_h']:.1f} | {m['final_vs_peak']:.2f} | {m['final_vs_first']:.2f} | {statut} |")

    for cohort in ("avant juin 2026", "apres juin 2026"):
        mets = [met_by_token[t["mint"]] for t in full if t["mint"] in met_by_token and t["cohort"] == cohort]
        if not mets:
            continue
        px = [m["peak_x"] for m in mets]
        dl = [m["delay_h"] for m in mets]
        gb = [m["final_vs_peak"] for m in mets]
        p72 = sum(1 for m in mets if m["delay_h"] <= 72) * 100 // len(mets)
        short = "avant 06/26" if cohort.startswith("avant") else "apres 06/26"
        lines.append(f"\n**Cohorte {cohort}** (n={len(mets)}) : pic median **{statistics.median(px):.2f}x** "
                     f"(moyenne {statistics.fmean(px):.2f}x), >=2x : {sum(1 for v in px if v >= 2)*100//len(px)}%, "
                     f"pic <=72h : {p72}%, "
                     f"delai median au pic **{statistics.median(dl):.1f} h**, "
                     f"fin/pic median **{statistics.median(gb):.2f}** "
                     f"(give-back {100*(1-statistics.median(gb)):.0f}%), "
                     f"actifs : {sum(1 for t in full if t['cohort']==cohort and t['active'])}/{len(mets)}.")

    all_m = list(met_by_token.values())
    launch_m = [met_by_token[t["mint"]] for t in full if t["mint"] in met_by_token and t["type"] == "launch"]
    for name, mets in (("Ensemble", all_m), ("Launches uniquement", launch_m)):
        if not mets:
            continue
        px = [m["peak_x"] for m in mets]
        dl = [m["delay_h"] for m in mets]
        gb = [m["final_vs_peak"] for m in mets]
        p72 = sum(1 for m in mets if m["delay_h"] <= 72) * 100 // len(mets)
        act = sum(1 for t in full if t["mint"] in met_by_token
                  and (name == "Ensemble" or t["type"] == "launch") and t["active"])
        lines.append(f"\n**{name} (n={len(mets)})** : pic median **{statistics.median(px):.2f}x**, "
                     f"moyenne {statistics.fmean(px):.2f}x (queue droite), >=2x : "
                     f"**{sum(1 for v in px if v >= 2)*100//len(mets)}%**, pic <=72h : **{p72}%**, "
                     f"delai median au pic "
                     f"**{statistics.median(dl):.1f} h**, fin/pic median **{statistics.median(gb):.2f}** "
                     f"(give-back {100*(1-statistics.median(gb)):.0f}%), "
                     f"encore cotes : {act}/{len(mets)}.")
    lines.append("")

    # ---------- Partie B ----------
    bt_ok = [t for t in tokens.values()
             if t["bt_rows"] is not None and t["life_days"] * 24 >= MIN_LIFE_BACKTEST_H]
    no_bt = [t for t in tokens.values() if t not in bt_ok]
    n_launch = sum(1 for t in bt_ok if t["type"] == "launch")
    lines.append(f"## Partie B — backtest de sortie (entree a la 1re bougie disponible)\n")
    lines.append(f"Tokens testables (vie >= 72h + serie partant de la naissance) : **{len(bt_ok)}/{len(tokens)}** "
                 f"(exclus : {', '.join(t['ticker'] for t in no_bt) or 'aucun'}). "
                 f"Dont **{n_launch} launches** (1re bougie open < {MAJOR_OPEN_THRESHOLD}$, bonding curve) "
                 f"et {len(bt_ok)-n_launch} majeurs/lisses (WETH, HYPE, AAPLX... : pas des launches, "
                 f"leur 'naissance' = borne de backfill).\n")
    lines.append("**Entree = close de la 1re bougie** (convention exécutable ; l'open de la 1re bougie d'un "
                 "launch est le print de creation a ~1e-12..1e-6$, inachetable en pratique — voir note en fin). "
                 "Serie la plus fine partant de la naissance : 1m > 15m > 1h (tolerance +2h). "
                 "Regle jamais declenchee = sortie a la derniere bougie (censuree).\n")
    lines.append("| Regle | n | Median | Moyenne | WR | Pire | Best | >=2x | Cens |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    rule_defs = [("hold24h (controle)", "hold", 24), ("hold 48h", "hold", 48),
                 ("hold 72h", "hold", 72), ("trailing -35%", "trail", None),
                 ("close < 50% du pic", "half", None)]

    def backtest(subset, entry_mode="close"):
        out = {}
        for label, kind, h in rule_defs:
            vals, cens = [], 0
            for tok in subset:
                entry = first_real_close(tok["bt_rows"]) if entry_mode == "close" else tok["bt_rows"][0][1]
                v, c = run_rule(tok["bt_rows"], kind, h, entry=entry)
                if v is not None:
                    vals.append(v)
                    cens += c
            s = stats_block(vals)
            s["cens"] = cens
            out[label] = s
        return out

    results = backtest(bt_ok)
    results_launch = backtest([t for t in bt_ok if t["type"] == "launch"])
    for label, _, _ in rule_defs:
        lines.append(f"| **{label}** " + fmt_s(results[label]) + f" {results[label]['cens']} |")
    lines.append("\n**Launches uniquement** (univers pertinent pour l'entree naissance) :\n")
    lines.append("| Regle | n | Median | Moyenne | WR | Pire | Best | >=2x | Cens |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for label, _, _ in rule_defs:
        lines.append(f"| **{label}** " + fmt_s(results_launch[label]) + f" {results_launch[label]['cens']} |")
    lines.append("\n*Cens = regle jamais declenchee, sortie a la derniere bougie (multiple 'encore ouvert'). "
                 f"Moyenne clipee a {MEAN_CLIP:.0f}x par trade (bornage des prints poussiere de bonding curve ; "
                 "mediane/WR/pire non clipses).*\n")

    # note convention open
    res_open = backtest(bt_ok, entry_mode="open")
    lines.append("Note — convention **entree = open de la 1re bougie** (theorique, non exécutable) : "
                 + ", ".join(f"{label} median {s['med']:.2f}x" for (label, _, _), s in zip(rule_defs, [res_open[l] for l, _, _ in rule_defs]))
                 + ". Les moyennes explosent (jusqu'a 1e6x) : certains launches ont un print de creation "
                 "a ~1e-12$ (AOC, 7STOCK) — preuve que l'open de la 1re bougie est inachetable, "
                 "d'ou la convention close de la 1re bougie non plate.\n")

    # detail par token de la regle trailing et half
    lines.append("### Detail par token (entree = close 1re bougie, serie utilisee)\n")
    lines.append("| Ticker | Type | Serie | Entree | Decalage vs naissance | hold24 | hold48 | hold72 | trail-35% | half-peak |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|")
    for tok in sorted(bt_ok, key=lambda t: t["birth"]):
        vals = []
        for label, kind, h in rule_defs:
            v, _ = run_rule(tok["bt_rows"], kind, h)
            vals.append(v)
        off_h = (tok["bt_rows"][0][0] - tok["birth"]) / MS_H
        lines.append(
            f"| {tok['ticker']} | {tok['type']} | {tok['bt_period']} "
            f"| {fmt_dt(tok['bt_rows'][0][0])[:16]} | {off_h:.1f}h "
            f"| {vals[0]:.2f}x | {vals[1]:.2f}x | {vals[2]:.2f}x | {vals[3]:.2f}x | {vals[4]:.2f}x |")

    # Winner (sur les launches = univers pertinent ; l'ensemble inclut des majeurs)
    best_label = max(results_launch, key=lambda k: results_launch[k]["med"])
    bs = results_launch[best_label]
    lines.append(f"\n## Regle gagnante (median, launches) : **{best_label}** — median {bs['med']:.2f}x, "
                 f"moyenne {bs['mean']:.2f}x, WR {bs['wr']*100:.0f}%, pire {bs['worst']:.3f}x, "
                 f"{bs['cens']} censure(s). (Sur l'ensemble launch+majeurs : "
                 f"{max(results, key=lambda k: results[k]['med'])} median "
                 f"{results[max(results, key=lambda k: results[k]['med'])]['med']:.2f}x.)\n")

    # ---------- Caveats ----------
    old = [t for t in bt_ok if (t["bt_rows"][0][0] - t["birth"]) > BIRTH_TOLERANCE_MS]
    lines.append("## Mises en garde explicites\n")
    lines.append("1. **Survivorship** : les tokens captures sont ceux VISIBLES par le collecteur fomo "
                 "(activite sociale / listing). Les morts-nes sans volume sont absents du corpus : "
                 "tous les multiples ci-dessus sont des **bornes HAUTES**. Le vrai univers des launches "
                 "a un pic median bien plus faible et un WR bien plus bas.")
    lines.append("2. **Detection a la naissance** : l'entree a la 1re bougie suppose de detecter le token "
                 "a sa 1re minute. Le collector live le fait, mais avec un delai (scan + fetch) : en reel, "
                 "l'entree se fait quelques minutes apres, a un prix souvent deja superieur (slippage "
                 "d'entree non modelise, fees non modelises).")
    lines.append("3. **Vieux tokens** : pour les tokens nes avant la periode du collector, la 1re bougie "
                 f"disponible part quand meme de la naissance proxy (serie 1h backfillee). {len(old)} "
                 "token(s) entres a plus de 2h de la naissance proxy (gaps de backfill).")
    lines.append("4. **Censure** : les regles trailing/-50% jamais declenchees sortent a la derniere "
                 "bougie — ces multiples sont 'encore ouverts', biais haussier pour les regles de sortie "
                 "si le token est encore vivant.")
    lines.append("5. **Etude, pas strategie** : pas de fees/slippage/funding. Toute transposition en "
                 "regle de stack doit passer par `scripts/stacked_portfolio.py run_stack` avant validation.\n")

    lines.append("## Comparaison v1 (corpus court, n=19) vs v2\n")
    px = [m["peak_x"] for m in all_m]
    dl = [m["delay_h"] for m in all_m]
    gb = [m["final_vs_peak"] for m in all_m]
    lpx = [m["peak_x"] for m in launch_m]
    lines.append("| Metrique | v1 (2026-09-27 matin) | v2 ensemble | v2 launches |")
    lines.append("|---|---|---|---|")
    lines.append(f"| Pic median | 3.18x | **{statistics.median(px):.2f}x** | {statistics.median(lpx):.2f}x |")
    lines.append(f"| >=2x | 58% | **{sum(1 for v in px if v >= 2)*100//len(px)}%** | "
                 f"{sum(1 for v in lpx if v >= 2)*100//len(lpx)}% |")
    lines.append(f"| Delai median au pic | 51.5 h | **{statistics.median(dl):.1f} h** | — |")
    lines.append(f"| Give-back median apres pic | 69% | **{100*(1-statistics.median(gb)):.0f}%** | — |\n")
    med_dl = statistics.median(dl)
    lines.append("Lecture : le corpus profond CHANGE la lecture v1. (a) Le 1m des launches nes sous le "
                 "collector voit les 15 premieres minutes : des pumps < 15 min etaient invisibles en 15m "
                 f"(AMBA : pic 1.14x en v1-15m vs ~93x en v2-1m). (b) Le delai median au pic explose "
                 f"(51.5h -> {med_dl:.0f}h) car le corpus profond contient des vies de 75-900 jours : le pic "
                 "n'est plus borne par la fenetre de capture. (c) Le give-back median reste massif "
                 f"(69% -> {100*(1-statistics.median(gb)):.0f}%) : la sortie mecanique reste la bonne famille de regles.\n")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK -> {OUT}")
    print(f"tokens={len(tokens)} lifecycle_n={len(all_m)} backtest_n={len(bt_ok)}")
    for k, s in results.items():
        print(f"  {k:24s} med={s['med']:.2f} mean={s['mean']:.2f} wr={s['wr']*100:.0f}% "
              f"worst={s['worst']:.3f} best={s['best']:.1f} cens={s['cens']}")


if __name__ == "__main__":
    main()
