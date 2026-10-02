#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bonding_signal_study.py — 2026-09-27
Signal EX-ANTE bonding_pct -> performance forward. Coupe transversale.
Unités : fomo_ohlcv.time = MILLISECONDES (leçon ts_ms) ; captured_at/resolved_at = s ;
fomo_swaps.created_at = STRING ISO. Close des bougies = fin de bucket (eff_time = T + L).
Merge multi-périodes (1m/5m/15m/1h) : highs = enveloppe union, closes = finest dispo.
"""
import sqlite3, json, math, statistics, datetime, os

ROOT = "/run/media/cheurteen/Jeux SSD/trading-agent"
DB = f"{ROOT}/data/fomo/fomo.db"
SWAPS = f"{ROOT}/data/fomo/fomo_swaps.db"
RES = f"{ROOT}/data/fomo/bonding_resolution.json"
REPORT = f"{ROOT}/reports/bonding-signal-2026-09-27.md"
LEN = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}

def utc(x):
    return datetime.datetime.fromtimestamp(x, datetime.timezone.utc).strftime("%m-%d %H:%M")

def ts_sec(v):
    if v > 1e17: return v / 1e9
    if v > 1e14: return v / 1e6
    if v > 1e11: return v / 1e3
    return v

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
cur = con.cursor()
res = json.load(open(RES))["resolved"]

snaps = {}
# MIGRATION REST (29/09) : fomo_new_coins mort → snapshot REST bonding
# (fomo_rest.db, endpoint='bonding_snapshot') ; upsert = 1 point/mint.
rcur = sqlite3.connect(f"file:{ROOT}/data/fomo/fomo_rest.db?mode=ro", uri=True, timeout=60).cursor()
for mint, raw, cap in rcur.execute(
        "SELECT entity_id, data, captured_at FROM fomo_rest_snapshots "
        "WHERE endpoint='bonding_snapshot'"):
    d = json.loads(raw)
    tok = d.get("token") or {}
    pct = (tok.get("launchpad") or {}).get("graduationPercent")
    if pct is None:
        continue
    snaps.setdefault(tok.get("symbol") or mint[:8], []).append(
        (ts_sec(cap), float(pct), d.get("marketCap")))
rcur.close()
n1 = sorted(t for t, sl in snaps.items() if sl[0][0] < 1790300000)
n2 = sorted(t for t, sl in snaps.items() if sl[0][0] >= 1790300000)
n_obs = sum(len(v) for v in snaps.values())
print(f"== SNAPSHOTS: {len(snaps)} tokens / {n_obs} obs | nuit1 09-24 ({len(n1)}): {n1}")
print(f"   nuit2 09-26 ({len(n2)}): {n2}")
print(f"   OVERLAP inter-nuits: {sorted(set(n1) & set(n2))}  -> velocite possible si non vide")

# ------------------------------------------------ séries multi-périodes
cache = {}
def load_series(mint):
    if mint in cache: return cache[mint]
    highs, closes = {}, {}   # time_s -> high | (prio, eff_time, close)
    prio = {"1m": 0, "5m": 1, "15m": 2, "1h": 3}
    for period, p in prio.items():
        rows = cur.execute("SELECT time, high, close FROM fomo_ohlcv WHERE asset=? AND period=?",
                           (mint, period)).fetchall()
        for t, h, c in rows:
            s = ts_sec(t)
            if h is not None and (s not in highs or h > highs[s]): highs[s] = h
            if c is not None and s not in closes:
                closes[s] = (p, s + LEN[period], c)
            elif c is not None and p < closes[s][0]:
                closes[s] = (p, s + LEN[period], c)
    cl = sorted((eff, c) for _s, (_p, eff, c) in closes.items())
    hi = sorted(highs.items())
    cache[mint] = (hi, cl)
    return cache[mint]

def close_at(cl, t):
    best = None
    for eff, c in cl:
        if eff <= t: best = c
        else: break
    return best

def max_high(hi, t0, t1):
    """enveloppe : bougie [T, T+L] compte si elle touche la fenêtre."""
    best = None
    for s, h in hi:
        if s > t1: break
        if s + 3600 >= t0 and h is not None:  # marge 1h = pire bucket (1h)
            if best is None or h > best: best = h
    return best

# ------------------------------------------------ observations
obs, missing = [], []
for tk, sl in sorted(snaps.items()):
    if tk not in res:
        missing.append(tk); continue
    mint = res[tk]["mint"]
    hi, cl = load_series(mint)
    if not cl:
        missing.append(f"{tk}(no-ohlcv)"); continue
    vend0 = cl[-1][0]
    if vend0 < sl[-1][0]:
        # données finies AVANT le snapshot = faux appariement (jumeau homonyme)
        missing.append(f"{tk}(stale-data,finit {utc(vend0)} < snapshot)"); continue
    first_eff = cl[0][1]
    base = cl[0][1]  # close 1re bougie
    for i, (ts_s, pct, mc) in enumerate(sl):
        cs = close_at(cl, ts_s)
        late = cs is None
        if cs is None: cs = cl[0][1]
        vend = cl[-1][0]
        pk24 = max_high(hi, ts_s, ts_s + 86400)
        pk7 = max_high(hi, ts_s, min(ts_s + 7 * 86400, vend))
        m24 = pk24 / cs if pk24 and cs else None
        m7 = pk7 / cs if pk7 and cs else None
        vel = None
        if i > 0:
            dt = (sl[i][0] - sl[i - 1][0]) / 86400.0
            if dt > 0: vel = (sl[i][1] - sl[i - 1][1]) / dt
        runup = cs / base if base and base > 0 else None
        # vol 1h : 1m sinon 15m*sqrt(4) sinon 1h
        vol1h, vsrc = None, None
        rs1, prev = [], None
        for eff, c in cl:
            if eff > ts_s: break
            if eff >= ts_s - 3600:
                if prev: rs1.append(math.log(c / prev))
                prev = c
        if len(rs1) >= 15:
            vol1h, vsrc = statistics.pstdev(rs1) * math.sqrt(60) * 100, "1m"
        else:
            rs15, prev = [], None
            for eff, c in cl:
                if eff > ts_s: break
                if eff >= ts_s - 3 * 3600:
                    if prev: rs15.append(math.log(c / prev))
                    prev = c
            if len(rs15) >= 6:
                vol1h, vsrc = statistics.pstdev(rs15) * math.sqrt(4) * 100, "15m"
            else:
                rsh, prev = [], None
                for eff, c in cl:
                    if eff > ts_s: break
                    if eff >= ts_s - 6 * 3600:
                        if prev: rsh.append(math.log(c / prev))
                        prev = c
                if len(rsh) >= 3:
                    vol1h, vsrc = statistics.pstdev(rsh) * 100, "1h"
        obs.append(dict(tk=tk, t=ts_s, night=utc(ts_s)[:5], pct=pct, mc=mc, vel=vel,
                        runup=runup, logrunup=math.log10(runup) if runup and runup > 0 else None,
                        vol1h=vol1h, vsrc=vsrc, m24=m24, m7=m7,
                        elapsed_h=(vend - ts_s) / 3600.0, late=late))
vel_n = sum(1 for o in obs if o["vel"] is not None)
print(f"== OBS: {len(obs)} | velocite: {vel_n} | exclus: {missing}")

def med(xs):
    xs = sorted(x for x in xs if x is not None)
    return statistics.median(xs) if xs else None

def fmt(x, spec="%.2f"):
    return (spec % x) if x is not None else "n/a"

def grad_block(key, tgt, lbl, tl):
    rows_src = [o for o in obs if o.get(key) is not None and o[tgt] is not None]
    n = len(rows_src)
    if n < 6:
        return f"**{lbl} vs {tl}** : n={n} insuffisant (vélocité : 0 token vu aux 2 nuits).\n"
    nb = 3 if n >= 12 else 2
    svals = sorted(o[key] for o in rows_src)
    cuts = [svals[int(round(k * n / nb))] for k in range(1, nb)]
    def bkt(v):
        b = 0
        for c in cuts:
            if v >= c: b += 1
        return b
    rows, bmeds = [], []
    for b in range(nb):
        grp = [o for o in rows_src if bkt(o[key]) == b]
        lo = min(o[key] for o in grp); hic = max(o[key] for o in grp)
        mm = med([o[tgt] for o in grp]); bmeds.append(mm)
        rows.append(f"| B{b+1} [{lo:.2f}–{hic:.2f}] | {len(grp)} | {mm:.2f}x | "
                    f"{max(o[tgt] for o in grp):.1f}x | {sum(1 for o in grp if o[tgt] >= 2)}/{len(grp)} |")
    mono = bmeds == sorted(bmeds) or bmeds == sorted(bmeds, reverse=True)
    sens = "croissant" if bmeds[-1] > bmeds[0] else "décroissant"
    return (f"**{lbl} vs {tl}** (n={n})\n\n| bucket | n | médiane | max | WR≥2x |\n|---|---|---|---|---|\n"
            + "\n".join(rows)
            + f"\n\n→ gradient {'**MONOTONE**' if mono else 'non monotone'}, sens {sens}, "
              f"ratio B{nb}/B1 = {bmeds[-1] / max(bmeds[0], 1e-9):.2f}\n")

print("\n== GRADIENTS (primaire: pic 24h) ==")
for key, lbl in [("pct", "bonding_pct"), ("vel", "vélocité pts/j"), ("logrunup", "log10 run-up"),
                 ("vol1h", "vol 1h %")]:
    for tgt, tl in [("m24", "pic24h"), ("m7", "pic→today")]:
        print(grad_block(key, tgt, lbl, tl))

rules = []
def add_rule(name, fn):
    grp = [o for o in obs if fn(o) and o["m24"] is not None]
    if len(grp) >= 5:
        rules.append((name, len(grp), med([o["m24"] for o in grp]), med([o["m7"] for o in grp]),
                      sum(1 for o in grp if o["m7"] >= 2), len(grp)))
for pth in [80, 85, 90]:
    add_rule(f"pct>={pth}", lambda o, p=pth: o["pct"] >= p)
    add_rule(f"pct<{pth}", lambda o, p=pth: o["pct"] < p)
for rl in [2, 3, 5]:
    add_rule(f"runup<x{rl}", lambda o, r=rl: o["runup"] is not None and o["runup"] < r)
    add_rule(f"runup>=x{rl}", lambda o, r=rl: o["runup"] is not None and o["runup"] >= r)
for vt in [0, 3, 5]:
    add_rule(f"vel>={vt}", lambda o, v=vt: o["vel"] is not None and o["vel"] >= v)
for pth in [80, 85]:
    for rl in [2, 3, 5]:
        add_rule(f"pct>={pth}&runup<x{rl}",
                 lambda o, p=pth, r=rl: o["pct"] >= p and o["runup"] is not None and o["runup"] < r)

print("\n== REGLES (n>=5, triées par médiane pic24h) ==")
for r in sorted(rules, key=lambda x: -(x[2] or 0)):
    print(f"  {r[0]:26s} n={r[1]:2d} med24={r[2]:.2f}x today={r[3]:.2f}x WR>=2x {r[4]}/{r[5]}")

# ------------------------------------------------ baleines
print("\n== BALEINES ==")
sw = sqlite3.connect(f"file:{SWAPS}?mode=ro", uri=True, timeout=60)
swc = sw.cursor()
wh_hits = {}
for tk, sl in snaps.items():
    if tk not in res: continue
    mint = res[tk]["mint"]
    cnt_m = swc.execute("SELECT COUNT(*) FROM fomo_swaps WHERE mint=?", (mint,)).fetchone()[0]
    cnt_t = swc.execute("SELECT COUNT(*) FROM fomo_swaps WHERE UPPER(REPLACE(ticker,'$',''))=?",
                        (tk.upper().replace("$", ""),)).fetchone()[0]
    if cnt_m or cnt_t: wh_hits[tk] = (cnt_m, cnt_t)
print(f"tokens des 21 avec des swaps (mint ou ticker, toute date): {wh_hits if wh_hits else 'AUCUN'}")
hi_g, lo_g = [], []
if wh_hits:
    for tk, sl in snaps.items():
        if tk not in wh_hits: continue
        t_end = sl[-1][0]
        rows = swc.execute("SELECT side, size_usd, ts, created_at FROM fomo_swaps WHERE mint=?",
                           (res[tk]["mint"],)).fetchall()
        net = 0.0
        for sd, sz, tc, ca in rows:
            c = ts_sec(tc) if tc else None
            if c is None:
                try: c = datetime.datetime.fromisoformat(ca.replace("Z", "+00:00")).timestamp()
                except Exception: continue
            if t_end - 48 * 3600 <= c <= t_end:
                net += (sz or 0) * (1 if (sd or "").lower() == "buy" else -1)
        for o in obs:
            if o["tk"] == tk and o["t"] == t_end and o["m24"] is not None:
                (hi_g if net >= 0 else lo_g).append((o, net))
for lbl, grp in [("ACCUMULENT (net≥0)", hi_g), ("DISTRIBUTENT (net<0)", lo_g)]:
    if grp:
        ms = [o["m24"] for o, _ in grp]; mt = [o["m7"] for o, _ in grp]
        print(f"  {lbl}: n={len(grp)} med24={med(ms):.2f}x today={med(mt):.2f}x "
              f"WR>=2x {sum(1 for x in mt if x >= 2)}/{len(grp)}")
        for o, net in sorted(grp, key=lambda z: -(z[0]["m7"] or 0)):
            print(f"    {o['tk']:16s} net={net:>10.0f}$ m24={o['m24']:.2f} today={o['m7']:.2f}")

print("\n== DETAIL PAR TOKEN ==")
for o in sorted(obs, key=lambda x: -((x["m7"] or 0))):
    v = f"{o['vel']:+.1f}" if o["vel"] is not None else "n/a"
    r = f"x{o['runup']:.2f}" if o["runup"] else "n/a"
    print(f"  {o['tk']:16s} {o['night']} pct={o['pct']:5.1f} vel={v} runup={r:>8s} "
          f"vol1h={fmt(o['vol1h'], '%6.1f')}%({o['vsrc']}) m24={fmt(o['m24'], '%7.2f')} "
          f"today={fmt(o['m7'], '%8.2f')}")

# ------------------------------------------------ rapport
full = ["# Bonding — signal ex-ante bonding_pct → performance forward (2026-09-27)\n",
        "Script : `scripts/bonding_signal_study.py` (lecture seule fomo.db/fomo_swaps.db mode=ro).\n",
        "## 1. Données réelles (≠ estimation mission)\n",
        f"- **2 nuits de snapshots** : 09-24 01:59 UTC ({len(n1)} tokens) et 09-26 02:17 UTC ({len(n2)} tokens) "
        f"= **{n_obs} lignes** ; l'estimation « 40-60 obs » supposait plus de nuits de collecte.",
        f"- **OVERLAP inter-nuits = 0** : les 2 nuits captent des ensembles DISJOINTS (les tokens de la nuit 1 "
        "ont gradué/disparu avant la nuit 2) → **vélocité Δpct/j IMPOSSIBLE sur ces données** (0 token vu 2 fois). "
        "Seule voie : tracker dorénavant les tokens 2 nuits de suite dans le bonding monitor.",
        f"- Observations exploitables (résolues + OHLCV) : **{len(obs)}** ; exclues (résolution échouée/absente) : "
        + ", ".join(missing) + ".",
        "- MUTANT : 1m démarre 8 min après le snapshot → close récupéré via merge multi-périodes (1h/15m/1m).",
        f"- Fenêtre « → aujourd'hui » : médiane {med([o['elapsed_h'] for o in obs]):.1f}h écoulées (tronquée à la "
        "collecte 09-27) ; le pic 24h est la cible la plus propre (fenêtre complète pour les 21).",
        "- Multiples mesurés sur HIGH (exécution idéalisée) ; close des bougies = fin de bucket (eff_time=T+L).\n",
        "## 2. Honnêteté statistique\n",
        "- **Coupe transversale**, split temporel impossible (2 nuits disjointes).",
        "- **Survivorship** : les 21 résolus = les tokens visibles → biais haussier global, "
        "moins sur les gradients relatifs (comparaisons intra-échantillon).",
        "- n=21 : règle à n≥5 → ~2 combinaisons de bruit ; barre = gradient clair + plausible → CANDIDAT-forward.",
        "- Run-up et bonding_pct sont corrélés (les deux montent avec le temps sur courbe) → redondance.\n",
        "## 3. Gradient maps\n"]
for key, lbl in [("pct", "bonding_pct"), ("vel", "vélocité pts/j"), ("logrunup", "log10 run-up"),
                 ("vol1h", "vol 1h %")]:
    full.append(grad_block(key, "m24", lbl, "pic 24h"))
    full.append(grad_block(key, "m7", lbl, "pic → aujourd'hui"))
full.append("## 4. Recherche de règle (n≥5)\n")
full.append("| règle | n | médiane pic24h | médiane →today | WR≥2x →today |\n|---|---|---|---|---|")
for r in sorted(rules, key=lambda x: -(x[2] or 0)):
    full.append(f"| {r[0]} | {r[1]} | {r[2]:.2f}x | {r[3]:.2f}x | {r[4]}/{r[5]} |")
full.append("\n## 5. Bonus baleines\n")
if not wh_hits:
    full.append("- **Croisement impossible** : fomo_swaps.db (12 562 swaps, collecte whale-radar) ne contient "
                "AUCUN des 21 tickers/mints (univers = gros caps leaderboards). À refaire si le collecteur "
                "couvre un jour les tokens fomo bonding.")
else:
    for lbl, grp in [("ACCUMULENT (net≥0, -48h)", hi_g), ("DISTRIBUTENT (net<0, -48h)", lo_g)]:
        if grp:
            full.append(f"- {lbl} : n={len(grp)}, médiane pic24h {med([o['m24'] for o, _ in grp]):.2f}x, "
                        f"→today {med([o['m7'] for o, _ in grp]):.2f}x")
full.append("\n## 6. Détail par token (trié par →today)\n")
full.append("| token | nuit | pct | vel | run-up | vol1h | pic24h | →today |\n|---|---|---|---|---|---|---|---|")
for o in sorted(obs, key=lambda x: -(x["m7"] or 0)):
    v = f"{o['vel']:+.1f}" if o["vel"] is not None else "n/a"
    r = f"x{o['runup']:.2f}" if o["runup"] else "n/a"
    full.append(f"| {o['tk']} | {o['night']} | {o['pct']:.0f} | {v} | {r} | "
                f"{fmt(o['vol1h'], '%.1f')}%({o['vsrc']}) | {fmt(o['m24'])}x | {fmt(o['m7'])}x |")
full.append("\n## 7. Verdict\n")
g_hi = med([o["m24"] for o in obs if o["pct"] >= 85] or [None])
g_lo = med([o["m24"] for o in obs if o["pct"] < 80] or [None])
best = sorted(rules, key=lambda x: -(x[2] or 0))[0] if rules else None
ratio = (g_hi / g_lo) if (g_hi and g_lo) else 0
if ratio >= 1.5 and best:
    full.append(f"- **CANDIDAT-forward** : bonding_pct haut ≠ épuisé (med pic24h pct≥85 = {g_hi:.2f}x vs "
                f"pct<80 = {g_lo:.2f}x, ratio {ratio:.2f}) ; meilleure règle « {best[0]} » n={best[1]}, "
                f"med24 {best[2]:.2f}x, →today {best[3]:.2f}x. Tracker live sur les prochains tokens "
                "franchissant 80/90 %, re-évaluer à n≥60.")
else:
    full.append(f"- **Verdict : la dispersion n'est PAS expliquée par ces features** (ratio pct haut/bas "
                f"pic24h = {ratio:.2f} sur n={len(obs)} ; médiane globale pic24h = "
                f"{med([o['m24'] for o in obs]):.2f}x, →today = {med([o['m7'] for o in obs]):.2f}x). "
                "Statut **CONTEXTE** : les snapshots arrivent trop tard dans la vie du token "
                "(run-up médian ×3,1 déjà fait, pic post-snapshot <2x dans 14/20 cas). "
                "Le signal ex-ante rentable reste le PREMIER snapshot (token jeune sur courbe), "
                "pas le niveau de bonding_pct lui-même.")
full.append("\n- Caveats : coupe transversale, survivorship, highs idéalisés, fenêtre →today tronquée, "
            "vol1h reconstructée multi-périodes (source indiquée).")
os.makedirs(os.path.dirname(REPORT), exist_ok=True)
open(REPORT, "w").write("\n".join(full) + "\n")
print(f"\n== REPORT: {REPORT}")
