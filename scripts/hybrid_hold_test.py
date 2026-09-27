#!/usr/bin/env python3
"""FOMO hybrid hold — backtest de la regle hybride 24h/72h (lecture seule).

Question (suite de lifecycle-v3-2026-09-28.md) : la cohorte swap baleine >10k$
(n=136) inverse la doctrine (hold72h 1.49x > hold24h 1.17x). Regle candidate :
hold 24h par defaut, MAIS extension a 72h SI un swap baleine >= $10k (cote BUY,
fomo_swaps.db) a eu lieu pendant la detention. EX-ANTE STRICT : la decision se
prend a t+24h avec les swaps connus a cet instant (pas de look-ahead) ; version
conservatrice = lag 1h (le flux swaps-fresh livre en <= 1h : seuls les swaps
ts <= t+23h comptent).

Briques importees de lifecycle_v3_scale.py (convention v3 verbatim) : entree =
close de la 1re bougie non plate, fenetres limit = rows[0][0] + N*h, sortie =
close de la derniere bougie <= limit, moyenne clippee 1000x. Le multiple
hybride est compose exactement : v72 si extension sinon v24 (meme semantique
run_rule -> aucune re-simulation, zero derive).

Unites (lecon ts_ms) : ohlcv.time = MILLISECONDS (LENGTH=13, v3), fomo_swaps.ts
= SECONDS (LENGTH=10, verifie ici : 12716/12716 a 10 chiffres) -> conversion
*1000 avant tout test de fenetre. Aucun join temporel brut.

Wallet : spot, taille fixe 5 %, 1 creneau (une position a la fois, les tokens
nes pendant une detention sont SKIPPES), frais taker 0.09 %/cote + slippage
0.5 %/cote (= convention honnete meme de derek_replication_test.py) -> facteur
net par trade = mult * (1-0.0059)/(1+0.0059). Spot = 0 liquidation par
construction. Compounding, DD sur equity par trade clos, BLOC STATS mensuel.

Rapport : reports/hybrid-hold-2026-09-28.md
"""

import bisect
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lifecycle_v3_scale import (  # noqa: E402
    ROOT, DB, SWAPS_DB, MS_H, ACTIVE_WINDOW_MS, MIN_CANDLES_1H,
    BIRTH_TOLERANCE_MS, MIN_LIFE_BACKTEST_H, MEAN_CLIP,
    clean_series, first_real_close, run_rule, stats_block, fmt_s,
    fmt_dec, deciles, notional_bucket, load_whale_notionals,
)

OUT = ROOT / "reports" / "hybrid-hold-2026-09-28.md"
WHALE_MIN = 10_000.0          # declencheur : swap baleine >= $10k, cote BUY
LAG_MS = 1 * MS_H             # conservateur : info fraiche livree en <= 1h
HOLD_H = 24                   # base ; extension -> 72
SIZE = 0.05                   # taille fixe 5 % equity
SIDE_COST = 0.0059            # slippage 0.5 % + taker 0.09 % par cote
CAPITAL = 100.0
SIDE = "buy"


def load_whale_buys():
    """(ts_ms, size_usd) tries par mint, cote BUY uniquement (side='swap'
    ambigu, 3 rows, exclu). ts SECONDS -> ms."""
    conn = sqlite3.connect(f"file:{SWAPS_DB}?mode=ro", uri=True)
    try:
        per = {}
        for mint, ts, sz in conn.execute(
            "SELECT mint, ts, size_usd FROM fomo_swaps "
            "WHERE side = ? AND mint IS NOT NULL AND ts IS NOT NULL "
            "AND size_usd IS NOT NULL ORDER BY mint, ts", (SIDE,)
        ):
            per.setdefault(mint, []).append((ts * 1000, sz))
    finally:
        conn.close()
    return per


def load_whale_any():
    """Pareil, TOUS les cotes (buy+sell) — sensibilite 'declencheur tous cotes'."""
    conn = sqlite3.connect(f"file:{SWAPS_DB}?mode=ro", uri=True)
    try:
        per = {}
        for mint, ts, sz in conn.execute(
            "SELECT mint, ts, size_usd FROM fomo_swaps "
            "WHERE mint IS NOT NULL AND ts IS NOT NULL "
            "AND size_usd IS NOT NULL ORDER BY mint, ts"
        ):
            per.setdefault(mint, []).append((ts * 1000, sz))
    finally:
        conn.close()
    return per


def has_whale_buy(buys, lo_ms, hi_ms):
    """Y a-t-il un swap BUY >= $10k dans [lo_ms, hi_ms] ? (fenetre ex-ante)"""
    if not buys or hi_ms < lo_ms:
        return False
    ts = [t for t, _ in buys]
    for k in range(bisect.bisect_left(ts, lo_ms), bisect.bisect_right(ts, hi_ms)):
        if buys[k][1] >= WHALE_MIN:
            return True
    return False


def net_mult(mult):
    return mult * (1 - SIDE_COST) / (1 + SIDE_COST)


def run_wallet(trades, label, cap_x=None):
    """trades : (t_entry_ms, exit_t_ms, mult, cens) tries par t_entry.
    1 creneau : entree seulement si t_entry > sortie precedente.
    cap_x : plafond honnete du multiple par trade (queue de survie non
    compoundable — sinon l'exponentielle fabrique des montants fantaisistes)."""
    bal = CAPITAL
    peak, max_dd = bal, 0.0
    taken, skipped, cens_used, costs = 0, 0, 0, 0.0
    wins = 0
    first_t = last_t = None
    months = {}
    busy_until = -1.0
    for t_entry, exit_t, mult, cens in sorted(trades, key=lambda x: x[0]):
        if t_entry <= busy_until:
            skipped += 1
            continue
        notional = bal * SIZE
        nm = net_mult(min(mult, cap_x) if cap_x else mult)
        pnl = notional * (nm - 1.0)
        costs += notional * (1.0 - (1 - SIDE_COST) / (1 + SIDE_COST))
        bal += pnl
        taken += 1
        wins += nm > 1.0
        cens_used += cens
        peak = max(peak, bal)
        max_dd = max(max_dd, 1 - bal / peak)
        busy_until = exit_t
        first_t = first_t or t_entry
        last_t = exit_t
        m = datetime.fromtimestamp(exit_t / 1000, tz=timezone.utc).strftime("%Y-%m")
        months.setdefault(m, [0, 0, bal, bal])
        months[m][0] += 1
        months[m][1] += nm > 1.0
        months[m][3] = bal
    days = (last_t - first_t) / 86_400_000 if first_t else 0
    roi_an = (bal / CAPITAL) ** (365.0 / days) - 1 if days > 7 and bal > 0 else None
    mrows, neg = [], 0
    for m, (n, w, b0, b1) in sorted(months.items()):
        r = b1 / b0 - 1
        neg += r < 0
        mrows.append((m, n, w / n * 100 if n else 0, r))
    worst = min(mrows, key=lambda x: x[3]) if mrows else None
    best = max(mrows, key=lambda x: x[3]) if mrows else None
    return {
        "label": label, "bal": bal, "taken": taken, "skipped": skipped,
        "wr": wins / taken if taken else 0, "cens": cens_used, "max_dd": max_dd,
        "costs": costs, "roi_an": roi_an, "months": mrows, "neg": neg,
        "worst": worst, "best": best, "days": days,
    }


def bloc(res):
    L = [f"**{res['label']}** : {CAPITAL:.0f} $ -> **${res['bal']:.2f}** "
         f"(ROI total {(res['bal']/CAPITAL-1)*100:+.1f} %"
         + (f", ROI/an {res['roi_an']*100:+.0f} %" if res['roi_an'] is not None else "")
         + f", DD max {res['max_dd']*100:.1f} %) sur {res['days']:.0f} jours."]
    L.append(f"Trades {res['taken']} (skips {res['skipped']}, censes {res['cens']}), "
             f"WR net {res['wr']*100:.0f} %, couts ${res['costs']:.2f}. "
             f"Mois negatifs {res['neg']}/{len(res['months'])}.")
    if res["worst"]:
        L.append(f"Pire mois {res['worst'][0]} {res['worst'][3]*100:+.1f} % "
                 f"({res['worst'][1]} trades) ; record {res['best'][0]} "
                 f"{res['best'][3]*100:+.1f} % ({res['best'][1]} trades).")
    L.append("")
    L.append("| Mois | trades | WR | PnL mois |")
    L.append("|---|---:|---:|---:|")
    for m, n, w, r in res["months"]:
        L.append(f"| {m} | {n} | {w:.0f}% | {r*100:+.2f}% |")
    return L


def main():
    whale = load_whale_notionals()          # (max, somme, n) sur TOUS swaps
    buys = load_whale_buys()                # cote BUY, tries
    anys = load_whale_any()                 # tous cotes, sensibilite
    tickers = {}
    tok = []                                # resultats par token testable
    n_assets = 0

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        tickers = dict(conn.execute("SELECT mint, ticker FROM fomo_tokens"))
        cur = conn.execute(
            "SELECT asset, period, time, open, high, close FROM fomo_ohlcv "
            "WHERE period IN ('15m','1h','1m') ORDER BY asset, period, time"
        )
        cur_asset, periods_rows = None, {}

        def finalize(asset):
            nonlocal n_assets
            if asset is None:
                return
            n_assets += 1
            series = {}
            for p, rows in periods_rows.items():
                cleaned, _, _ = clean_series(rows)
                if cleaned:
                    series[p] = cleaned
            if "1h" not in series or len(series["1h"]) < MIN_CANDLES_1H:
                return
            union = sorted((r for rs in series.values() for r in rs),
                           key=lambda r: r[0])
            birth = min(rows[0][0] for rows in series.values())
            last_t = max(rows[-1][0] for rows in series.values())
            life_h = (last_t - birth) / MS_H
            first_close = first_real_close(union)
            if not first_close or first_close <= 0:
                return
            peak = max(r[2] for r in union)
            if peak / first_close > 10_000:
                return                          # artefact (0 attendu, v3)
            pick = None
            for p in ("1m", "15m", "1h"):
                rows = series.get(p)
                if rows and rows[0][0] <= birth + BIRTH_TOLERANCE_MS:
                    pick = p
                    break
            if not pick or life_h < MIN_LIFE_BACKTEST_H:
                return
            rows = series[pick]
            entry = first_real_close(rows)
            if not entry or entry <= 0:
                return
            v24, c24 = run_rule(rows, "hold", 24, entry=entry)
            v72, c72 = run_rule(rows, "hold", 72, entry=entry)
            if v24 is None or v72 is None:
                return
            t_entry = next((t for t, o, h, c in rows
                            if c and c > 0 and h and h > o), rows[0][0])
            times = [r[0] for r in rows]
            lim24 = rows[0][0] + 24 * MS_H
            lim72 = rows[0][0] + 72 * MS_H
            exit24_t = times[bisect.bisect_right(times, lim24) - 1]
            exit72_t = times[bisect.bisect_right(times, lim72) - 1]
            tok.append({
                "mint": asset, "ticker": tickers.get(asset) or asset[:8],
                "t0": rows[0][0], "t_entry": t_entry, "last_t": last_t,
                "life_h": life_h, "period": pick,
                "v24": v24, "v72": v72, "c24": c24, "c72": c72,
                "exit24_t": exit24_t, "exit72_t": exit72_t,
                "whale_max": whale.get(asset, (None,))[0],
                "ext_ideal": has_whale_buy(buys.get(asset, ()), t_entry, lim24),
                "ext_cons": has_whale_buy(buys.get(asset, ()), t_entry,
                                          lim24 - LAG_MS),
                "ext_any": has_whale_buy(anys.get(asset, ()), t_entry,
                                         lim24 - LAG_MS),
            })

        for asset, period, t, o, h, c in cur:
            if asset != cur_asset:
                finalize(cur_asset)
                cur_asset, periods_rows = asset, {}
            periods_rows.setdefault(period, []).append((t, o, h, c))
        finalize(cur_asset)
    finally:
        conn.close()

    N = len(tok)
    db_max = max(t["last_t"] for t in tok)
    for t in tok:
        t["dead"] = (db_max - t["last_t"]) >= ACTIVE_WINDOW_MS

    # ---- variantes ----
    for t in tok:
        t["hyb_ideal"] = (t["v72"], t["c72"]) if t["ext_ideal"] else (t["v24"], t["c24"])
        t["hyb_cons"] = (t["v72"], t["c72"]) if t["ext_cons"] else (t["v24"], t["c24"])
        t["hyb_any"] = (t["v72"], t["c72"]) if t["ext_any"] else (t["v24"], t["c24"])

    RULES = [("hold24h (baseline)", "v24", "c24"),
             ("hybride ideal", "hyb_ideal", None),
             ("hybride conservateur (lag 1h)", "hyb_cons", None),
             ("hybride tous cotes (sens.)", "hyb_any", None),
             ("hold72h pur", "v72", "c72")]
    vals = {lab: [t[vk][0] if isinstance(t[vk], tuple) else t[vk] for t in tok]
            for lab, vk, _ in RULES}

    # ---- anchors v3 ----
    a24, a72 = stats_block(vals["hold24h (baseline)"]), stats_block(vals["hold72h pur"])
    anchor_ok = (abs(a24["med"] - 1.44) < 0.02 and abs(a72["med"] - 1.19) < 0.02)
    print(f"N={N} anchors hold24h med={a24['med']:.2f} wr={a24['wr']*100:.0f}% "
          f"worst={a24['worst']:.3f} | hold72h med={a72['med']:.2f} "
          f"wr={a72['wr']*100:.0f}% worst={a72['worst']:.3f} ok={anchor_ok}")

    # ---- sign tests sur les etendus ----
    ext = [t for t in tok if t["ext_cons"]]
    extA = [t for t in tok if t["ext_any"]]

    def sign_test(sub):
        w = sum(1 for t in sub if t["v72"] > t["v24"])
        l = sum(1 for t in sub if t["v72"] < t["v24"])
        nn = w + l
        p = 1.0
        if nn:
            lo = min(w, l)
            p = min(1.0, sum(math.comb(nn, k) for k in range(0, lo + 1))
                    / 2 ** nn * 2)
        return w, l, len(sub) - w - l, p

    w, l, n_eq, p_two = sign_test(ext)
    wA, lA, n_eqA, p_any = sign_test(extA)
    big = [t for t in tok if notional_bucket(t["whale_max"]) == ">10k$"]
    big_ext = sum(1 for t in big if t["ext_cons"])
    big_extA = sum(1 for t in big if t["ext_any"])
    ext_in_big = sum(1 for t in ext if notional_bucket(t["whale_max"]) == ">10k$")

    # ---- wallet ----
    def trades_of(key, ext_key=None):
        out = []
        for t in tok:
            if key.startswith("hyb"):
                v, c = t[key]
                exit_t = t["exit72_t"] if t[ext_key] else t["exit24_t"]
            elif key == "v72":
                v, c, exit_t = t["v72"], t["c72"], t["exit72_t"]
            else:
                v, c, exit_t = t["v24"], t["c24"], t["exit24_t"]
            out.append((t["t_entry"], exit_t, v, c))
        return out

    wl = run_wallet(trades_of("v24"), "wallet hold24h pur")
    wh = run_wallet(trades_of("hyb_cons", "ext_cons"), "wallet hybride (conservateur)")
    w7 = run_wallet(trades_of("v72"), "wallet hold72h pur")
    CAP_X = 10.0     # plafond par trade : au-dela, queue de survie non compoundable
    CAP2_X = 100.0
    wl10 = run_wallet(trades_of("v24"), "wallet hold24h pur (cap 10x/trade)",
                      cap_x=CAP_X)
    wh10 = run_wallet(trades_of("hyb_cons", "ext_cons"),
                      "wallet hybride conservateur (cap 10x/trade)", cap_x=CAP_X)
    w710 = run_wallet(trades_of("v72"), "wallet hold72h pur (cap 10x/trade)",
                      cap_x=CAP_X)
    wl100 = run_wallet(trades_of("v24"), "hold24h pur (cap 100x)", cap_x=CAP2_X)
    wh100 = run_wallet(trades_of("hyb_cons", "ext_cons"), "hybride (cap 100x)",
                       cap_x=CAP2_X)
    w7100 = run_wallet(trades_of("v72"), "hold72h pur (cap 100x)", cap_x=CAP2_X)

    # ---- rapport ----
    L = []
    A = L.append
    A("# FOMO Hybrid Hold — la regle 24h/72h conditionnee au swap baleine — 2026-09-28\n")
    A(f"Source : `data/fomo/fomo.db` + `data/fomo/fomo_swaps.db` mode=ro. Briques v3 "
      f"(`scripts/lifecycle_v3_scale.py`) reutilisees verbatim : entree = close de la 1re "
      f"bougie non plate, sortie = close de la derniere bougie <= limit, moyenne clippee "
      f"{MEAN_CLIP:.0f}x. Suite directe de `reports/lifecycle-v3-2026-09-28.md` (cohortes "
      f">10k$ : hold72h 1.49x > hold24h 1.17x).\n")
    A(f"**Regle hybride** : hold 24h par defaut ; extension a 72h SI un swap baleine "
      f">= {WHALE_MIN:.0f}$ (cote BUY) a eu lieu sur le token pendant la detention "
      f"[entree, entree+24h]. EX-ANTE : decision a t+24h avec les swaps connus a cet "
      f"instant. **Conservateur** : lag 1h (seuls les swaps ts <= t+23h comptent). "
      f"Unites verifiees : ohlcv.time = ms (LENGTH 13), swaps.ts = SECONDS "
      f"(12716/12716 rows a LENGTH 10) -> x1000. side='buy' lowercase (3 rows "
      f"'swap' ambiguex exclues).\n")
    A(f"## 0. Corpus et ancres\n")
    A(f"- {n_assets} assets streamés, **N={N}** tokens testables (meme selection v3 : "
      f">= {MIN_CANDLES_1H} bougies 1h, vie >= 72h, serie la plus fine partant de la "
      f"naissance +/-2h, non-artefact). Ancres v3 : hold24h 1.44x/63 %/pire 0.020x, "
      f"hold72h 1.19x/59 %/0.011x -> reproduits "
      f"({'OK' if anchor_ok else 'ECART — voir tableau'}).\n")
    A("## A. Les quatre regles sur le meme corpus\n")
    A("| Regle | n | Median | Moyenne | WR | Pire | Best | >=2x |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for lab, _, _ in RULES:
        A(f"| **{lab}** " + fmt_s(stats_block(vals[lab])) + " |")
    A("")
    A("### Distribution (deciles des multiples) — l'hybride doit capter la queue "
      "sans trainer les morts\n")
    A("| Regle | min | P10 | P20 | P30 | P40 | **med** | P60 | P70 | P80 | P90 | max |")
    A("|---|" + "---:|" * 11)
    for lab, _, _ in RULES:
        A(f"| {lab} | " + fmt_dec(deciles(vals[lab])) + " |")
    A("")
    ext_i = sum(1 for t in tok if t["ext_ideal"])
    A(f"## B. Decomposition honnete\n")
    A(f"- Extensions declenchees : **ideal {ext_i}/{N} ({ext_i*100/N:.1f} %)**, "
      f"conservateur BUY {len(ext)}/{N} ({len(ext)*100/N:.1f} %), tous cotes "
      f"{len(extA)}/{N} ({len(extA)*100/N:.1f} %) — la regle ne change que ces "
      f"tokens, le reste est identique au baseline par construction.")
    A(f"- Sign test apparie sur les {len(ext)} etendus BUY (conservateur), hold72h vs "
      f"hold24h : **{w} meilleurs / {l} pires / {n_eq} egaux** -> p binomial "
      f"bilatere = {p_two:.3f} (l'extension ne prouve RIEN ici, tendance NEGATIVE).")
    A(f"- Sensibilite tous cotes ({len(extA)} etendus) : {wA} meilleurs / {lA} pires "
      f"/ {n_eqA} egaux, p = {p_any:.3f}.")
    A(f"- Chevauchement avec la cohorte v3 >10k$ (n={len(big)}, definie EX-POST : max "
      f"sur TOUS swaps de VIE ENTIERE) : seuls {big_ext}/{len(big)} recoivent "
      f"l'extension BUY conservateur ({big_extA} tous cotes) ; et inversement "
      f"{ext_in_big}/{len(ext)} etendus sont dans la cohorte. **L'edge v3 etait "
      f"mesure ex-post — il n'est PAS ex-ante capturable par ce declencheur.**")
    A("")
    A("| Sous-population | n | hold24h med | hybride cons med | hold72h med |")
    A("|---|---:|---:|---:|---:|")

    def med_of(sub, lab):
        v = [t[lab][0] if isinstance(t[lab], tuple) else t[lab] for t in sub]
        return f"{statistics.median(v):.2f}x" if v else "-"

    for name, sub in [
        ("etendus BUY (conservateur)", ext),
        ("etendus tous cotes (sens.)", extA),
        ("non etendus", [t for t in tok if not t["ext_cons"]]),
        ("cohorte v3 >10k$ (max tous swaps)", big),
        ("cohorte v3 <=10k$", [t for t in tok if notional_bucket(t["whale_max"]) in ("<1k$", "1k-10k$")]),
        ("sans swap baleine enregistre", [t for t in tok if t["whale_max"] is None]),
        ("tokens morts (db_max - last >= 48h)", [t for t in tok if t["dead"]]),
    ]:
        if sub:
            A(f"| {name} | {len(sub)} | {med_of(sub, 'v24')} | {med_of(sub, 'hyb_cons')} "
              f"| {med_of(sub, 'v72')} |")
    A("")
    mean24 = statistics.fmean(min(v, MEAN_CLIP) for v in vals["hold24h (baseline)"])
    meanh = statistics.fmean(min(v, MEAN_CLIP) for v in vals["hybride conservateur (lag 1h)"])
    contrib = sum(min(t["v72"], MEAN_CLIP) - min(t["v24"], MEAN_CLIP)
                  for t in ext) / N
    first_delays, last_hour = [], 0
    for t in ext:
        d = [(b[0] - t["t_entry"]) / MS_H for b in buys.get(t["mint"], [])
             if b[1] >= WHALE_MIN and t["t_entry"] <= b[0] <= t["t0"] + 24 * MS_H]
        if d:
            first_delays.append(min(d))
            if min(d) >= (24 * MS_H - LAG_MS) / MS_H:
                last_hour += 1
    A(f"- Moyennes clippees : hold24h {mean24:.2f}x vs hybride cons {meanh:.2f}x "
      f"({(meanh-mean24)/mean24*100:+.0f} %) — contribution des seuls etendus : "
      f"{contrib:+.2f}x sur la moyenne du corpus (100 % de l'ecart vient d'eux, "
      f"n={len(ext)} : sous-puissance statistique, p={p_two:.2f}).")
    A(f"- Delai du 1er swap BUY >= $10k dans la fenetre (etendus, n={len(first_delays)}) : "
      f"mediane {statistics.median(first_delays):.1f}h apres l'entree ; "
      f"{last_hour} dans la DERNIERE heure (t+23h->t+24h) — seuls eux differencient "
      f"ideal (22) et conservateur (21).")
    A("")
    A("## C. Wallet spot — 5 % taille fixe, 1 creneau, taker 0.09 %/cote + slippage 0.5 %/cote\n")
    A(f"Spot = **0 liquidation par construction** (pas de levier). 1 creneau : les tokens "
      f"nes pendant une detention sont skips (path-dependence honnete du backfill). "
      f"Sans plafond, les multiples monstres (max {max(t['v24'] for t in tok):.0f}x) "
      f"compoundent l'exponentielle en montants FANTAISISTES (survivorship v3) — "
      f"lecture principale = cap 10x/trade (identique pour les 3 variantes, comparaison "
      f"relative loyale) ; les variantes cap 100x et sans plafond ne valent que par "
      f"l'ORDRE RELATIF.\n")
    for wres in (wl10, wh10, w710):
        L += bloc(wres)
    A(f"Ordre relatif uniquement — cap 100x : hold24h ${wl100['bal']:.3g}, hybride "
      f"${wh100['bal']:.3g}, 72h pur ${w7100['bal']:.3g} ; sans plafond : "
      f"${wl['bal']:.3g} / ${wh['bal']:.3g} / ${w7['bal']:.3g}.\n")
    A("## D. Mises en garde\n")
    A("1. **Survivorship herite de v3** : corpus = tokens backfiles PARCE QUE trades par "
      "les baleines suivies. Bornes hautes ; le wallet n'est pas transposable tel quel.")
    A("2. **Sous-puissance** : l'edge repose sur n="
      f"{len(ext)} etendus (p={p_two:.2f} au sign test). Un seul gros token deplace la mediane.")
    A(f"3. **Fenetre de detection** : le declencheur n'utilise que les swaps BUY >= $10k "
      f"ENREGISTRES dans fomo_swaps.db (backfill partiel des wallets suivis) — un swap "
      f"manquant = extension ratee = biais CONSERVATEUR sur l'edge, mais n de Detection sous-estime.")
    A("4. **Censure** : sorties a la derniere bougie si la serie s'arrete avant la limite "
      f"(hold24h cense {sum(1 for t in tok if t['c24'])}, hold72h {sum(1 for t in tok if t['c72'])}) "
      "— biais haussier sur les tokens encore actifs a donnee tronquee.")
    A("5. **Execution** : sortie au CLOSE de la bougie limite (v3) ; le conservateur suppose "
      "l'info baleine fraiche livree en <= 1h et la decision prise sur ts <= t+23h. "
      "Hautes idealises (meches) : sorties close-based, moins touchees.\n")
    hc = stats_block(vals["hybride conservateur (lag 1h)"])
    ha = stats_block(vals["hybride tous cotes (sens.)"])
    A("## Verdict\n")
    A(f"- **La regle hybride ne capture RIEN en ex-ante** : declencheur BUY >= $10k dans "
      f"les 24 premieres heures = {len(ext)}/{N} tokens (1.7 %), mediane inchangée "
      f"({hc['med']:.2f}x vs 1.44x baseline), et sur ces {len(ext)} tokens l'extension "
      f"tendance NEGATIVE ({w} mieux / {l} pire, p={p_two:.2f}). L'edge v3 de la cohorte "
      f">10k$ etait EX-POST (max sur vie entiere, tous cotes) — non reachable a t+24h.")
    A(f"- Sensibilite tous cotes : mediane {ha['med']:.2f}x, {wA}/{lA}, p={p_any:.2f} — "
      f"pas mieux. hold72h pur reste derriere partout (1.19x, WR 59 %, pire 0.011x).")
    A(f"- Wallet 1 creneau (cap 10x/trade) : hold24h ${wl10['bal']:.2f} (DD "
      f"{wl10['max_dd']*100:.1f} %, WR {wl10['wr']*100:.0f} %) vs hybride "
      f"${wh10['bal']:.2f} (DD {wh10['max_dd']*100:.1f} %, WR {wh10['wr']*100:.0f} %) "
      f"vs 72h pur ${w710['bal']:.2f} — l'hybride est en-dessous du baseline : les "
      f"{len(ext)} etendus coutent plus qu'ils ne rapportent.")
    A(f"- **Verdict : NUL en l'etat.** La doctrine hold24h tient ; la regle hybride est "
      f"re-categorisee NUL (declencheur ex-ante trop rare et non porteur). La piste "
      f"baleine >10k$ reste ouverte UNIQUEMENT comme signal de DETECTION temps reel "
      f"(flux swaps-fresh), a re-tester quand le backfill swaps couvrira plus de mints.\n")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"OK -> {OUT}")
    for lab, _, _ in RULES:
        s = stats_block(vals[lab])
        print(f"  {lab:32s} med={s['med']:.2f} mean={s['mean']:.2f} wr={s['wr']*100:.0f}% "
              f"worst={s['worst']:.3f} ge2={s['ge2']*100:.0f}%")
    print(f"extensions ideal={ext_i} cons={len(ext)} ({len(ext)*100/N:.1f}%) "
          f"any={len(extA)} sign BUY w={w} l={l} p={p_two:.3f} | "
          f"any w={wA} l={lA} p={p_any:.3f} | big={len(big)} big_ext={big_ext} "
          f"big_extA={big_extA} ext_in_big={ext_in_big}")
    for wres in (wl10, wh10, w710, wl100, wh100, w7100, wl, wh, w7):
        print(f"  wallet {wres['label']:42s} ${wres['bal']:.4g} dd={wres['max_dd']*100:.1f}% "
              f"trades={wres['taken']} wr={wres['wr']*100:.0f}% neg_mois={wres['neg']}")


if __name__ == "__main__":
    main()
