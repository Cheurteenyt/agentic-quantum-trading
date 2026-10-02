# INV-I — « LA TRACE DE BALEINE » — one-shot (gouvernance docs/38, tag freeze-2026-10-02)
# ARCHIVÉ (02/10/2026) — INV-I : FAIL pleine puissance, le print individuel = découpage d'ordre (docs/38)
# Pré-enregistrement : reports/aster/inv-i-trace-baleine-2026-10.md
# Seal sha256 du pré-enregistrement : 0deb85f1aa49eafdb1db7866dc2be9068eca6481022c8159745ee7869d3ebba3
# Exécution UNIQUE — aucun re-run de variante autorisé (budget = 1 expérience).
# Données : data/warehouse/klines.db LECTURE SEULE (mode=ro). 1x sans levier, 18 bps RT, 0 liq par construction.
import sqlite3
import numpy as np

DB = 'file:data/warehouse/klines.db?mode=ro'
COST = 0.0018          # 18 bps A/R, pré-déclaré
T5, GAP5 = 300_000, 600_000        # +5 min, tolérance 10 min (pré-déclaré)
T24, T4 = 86_400_000, 14_400_000   # +24 h principal, +4 h secondaire
AVA, IMP = 0.0010, 0.0030          # ±0,10 % / ≥0,30 % (pré-déclaré)

# ── chargement + tri canonique (ts_ms, agg_id) — JAMAIS ts seul (piège des reculs) ──
con = sqlite3.connect(DB, uri=True)
SYMS = ('BTCUSDT', 'ETHUSDT')
data = {}
for sym in SYMS:
    rows = con.execute(
        "SELECT agg_id, ts_ms, price, qty, is_buyer_maker FROM aster_tape WHERE symbol=? ORDER BY agg_id",
        (sym,)).fetchall()
    a = np.array(rows, dtype=np.float64)
    order = np.lexsort((a[:, 0], a[:, 1]))          # (ts_ms, agg_id)
    data[sym] = {k: a[order, i] for i, k in enumerate(('agg', 'ts', 'px', 'qty', 'imb'))}
    del rows, a, order
con.close()

# assertion unité ts_ms (millisecondes, couverture 2026) — leçon ts_ms
allts = np.concatenate([data[s]['ts'] for s in SYMS])
assert 1_767_225_600_000 < allts.min() < allts.max() < 1_798_363_200_000, 'unité ts_ms invalide'

T_SPLIT = float(np.quantile(allts, 0.60))           # split 60/40 chrono GLOBAL, un seul bornage
print(f"T_split = {T_SPLIT:.0f} ms = {np.datetime64(int(T_SPLIT), 'ms')}")
print(f"prints : {', '.join(f'{s} {len(data[s]['ts'])}' for s in SYMS)}")

# ── seuils q99 par symbole, TRAIN SEULEMENT (figés, appliqués tels quels en VAL) ──
thr = {s: float(np.quantile(data[s]['qty'][data[s]['ts'] < T_SPLIT], 0.99)) for s in SYMS}
for s in SYMS:
    print(f"q99 TRAIN {s} = {thr[s]:.6f} (unités base)")

recs = []   # (sym, ts0, px0, p5, p24, p4, dir, cls, ret24, ret4h, split, qrank, ts_exit)
excl = {s: {'fin_data': 0, 'gap5': 0, 'gap24': 0, 'zone_morte': 0, 'contraire': 0} for s in SYMS}
for s in SYMS:
    d = data[s]
    ts, px, qty, imb = d['ts'], d['px'], d['qty'], d['imb']
    idx = np.where(qty >= thr[s])[0]                # événement = UN print ≥ q99 (zéro grille)
    # quintiles de taille d'événements TRAIN (bornes figées, appliquées aux 2 splits)
    ev_train_sz = qty[idx[ts[idx] < T_SPLIT]]
    qb = np.quantile(ev_train_sz, [0.2, 0.4, 0.6, 0.8])
    print(f"{s}: {len(idx)} événements (TRAIN {len(ev_train_sz)}) ; bornes quintiles TRAIN = "
          f"{qb[0]:.4f}/{qb[1]:.4f}/{qb[2]:.4f}/{qb[3]:.4f}")
    t0 = ts[idx]
    # CORRECTION incident v1 : les indices j5/j4/j24 portent sur le tableau COMPLET
    # (len(ts) ~ 6,2 M) — la v1 les comparait à len(idx) (~65 k) → fausse exclusion
    # de masse « fin_data ». Aucun seuil/critère/fenêtre touché — bornage seul.
    N = len(ts)
    j5 = np.searchsorted(ts, t0 + T5)
    j4 = np.searchsorted(ts, t0 + T4)
    j24 = np.searchsorted(ts, t0 + T24)
    for k in range(len(idx)):
        i, ts_ = idx[k], t0[k]
        split = 0 if ts_ < T_SPLIT else 1
        if j5[k] >= N:
            excl[s]['fin_data'] += 1
            continue
        p5, p0 = px[j5[k]], px[i]
        if ts[j5[k]] > ts_ + T5 + GAP5:
            excl[s]['gap5'] += 1
            continue
        ratio = p5 / p0 - 1.0
        dr = 1.0 - 2.0 * imb[i]                     # convention gelée : imb=0 → +1 (taker buy)
        if abs(ratio) <= AVA:
            cls, dtr = 'AVALE', -dr
        elif ratio * dr >= IMP:
            cls, dtr = 'IMPACTANT', dr
        else:
            excl[s]['zone_morte' if abs(ratio) <= IMP else 'contraire'] += 1
            continue
        if j24[k] >= N or ts[j24[k]] > ts_ + T24 + GAP5:
            excl[s]['gap24'] += 1
            continue
        p24 = px[j24[k]]
        ret24 = dtr * (p24 / p5 - 1.0) - COST
        ret4 = np.nan
        if j4[k] < N and ts[j4[k]] <= ts_ + T4 + GAP5:
            ret4 = dtr * (px[j4[k]] / p5 - 1.0) - COST
        qrank = int(np.searchsorted(qb, qty[i], side='right')) + 1   # 1..5
        recs.append((s, ts_, p0, p5, p24, dr, cls, ret24, ret4, split, qrank, ts[j24[k]]))

import collections
cls_cnt = collections.Counter((r[0], r[9], r[6]) for r in recs)
print("\nExclusions :", {s: dict(excl[s]) for s in SYMS})
for s in SYMS:
    for sp in (0, 1):
        a = cls_cnt[(s, sp, 'AVALE')]
        b = cls_cnt[(s, sp, 'IMPACTANT')]
        print(f"  {s} split {'TRAIN' if sp == 0 else 'VAL'} : AVALÉ {a} / IMPACTANT {b}")

R = np.array(recs, dtype=object)
ts0 = np.array([r[1] for r in recs])
ret24 = np.array([r[7] for r in recs])
ret4 = np.array([r[8] for r in recs], dtype=np.float64)
cls = np.array([r[6] for r in recs])
split = np.array([r[9] for r in recs])
qr = np.array([r[10] for r in recs])
syms = np.array([r[0] for r in recs])

# ── espérances par split × classe ──
def stats(x):
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return (0, np.nan, np.nan, np.nan, np.nan)
    return (len(x), x.mean(), np.median(x), (x > 0).mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))

print("\n═══ ESPÉRANCE NETTE PAR BRANCHE (ret +5 min → +24 h, 18 bps déduits) ═══")
crit2 = True
for sp, nm in ((0, 'TRAIN'), (1, 'VAL')):
    for c in ('AVALE', 'IMPACTANT'):
        n_, m_, md_, wr_, t_ = stats(ret24[(split == sp) & (cls == c)])
        n4, m4 = stats(ret4[(split == sp) & (cls == c)])[:2]
        ok = m_ > 0
        crit2 &= ok
        print(f"  {nm} {c:9s}: n={n_:6d} moy={m_*100:+.3f} % méd={md_*100:+.3f} % WR={wr_*100:.1f} % "
              f"t={t_:+.2f} | +4h moy={m4*100:+.3f} % [{'OK' if ok else 'ECHEC'}]")
c1 = {c: int(((split == 0) & (cls == c)).sum()) for c in ('AVALE', 'IMPACTANT')}
print(f"  C1 n_train par classe : {c1} → {'OK' if all(v >= 100 for v in c1.values()) else 'SOUS-PUISSENT'}")

print("\n═══ C3 GRADIENT QUINTILES DE TAILLE (poolé, espérance nette) ═══")
c3 = True
for sp, nm in ((0, 'TRAIN'), (1, 'VAL')):
    means = []
    for q in (1, 2, 3, 4, 5):
        n_, m_, *_ = stats(ret24[(split == sp) & (qr == q)])
        means.append(m_)
        print(f"  {nm} Q{q}: n={n_:6d} moy={m_*100:+.3f} %")
    mono = all(means[i] <= means[i + 1] + 1e-12 for i in range(4))
    c3 &= mono
    print(f"  {nm} monotone Q1→Q5 : {'OK' if mono else 'ECHEC'}")

print("\n═══ C4 CONTRÔLE INVERSE (sens des classes échangé, poolé) ═══")
# inverse net = -(gross flip) - coût : inv = -ret - 2*COST (le flip ne rend PAS les frais)
c4 = True
for sp, nm in ((0, 'TRAIN'), (1, 'VAL')):
    f = ret24[split == sp]
    n_f, m_f, *_ = stats(f)
    n_i, m_i, *_ = stats(-f - 2 * COST)
    ok = m_f > m_i
    c4 &= ok
    print(f"  {nm}: forward {m_f*100:+.3f} % (n={n_f}) vs inverse {m_i*100:+.3f} % → {'BATTU' if ok else 'NON BATTU'}")
    for c in ('AVALE', 'IMPACTANT'):
        m1 = stats(ret24[(split == sp) & (cls == c)])[1]
        m2 = stats(-ret24[(split == sp) & (cls == c)] - 2 * COST)[1]
        print(f"    {c:9s}: forward {m1*100:+.3f} % vs inverse {m2*100:+.3f} % (descriptif)")

print(f"\nC2 (2 branches > 0 TRAIN ET VAL) : {'OK' if crit2 else 'ECHEC'} ; C3 : {'OK' if c3 else 'ECHEC'} ; "
      f"C4 : {'OK' if c4 else 'ECHEC'}")
verdict = (all(v >= 100 for v in c1.values()) and crit2 and c3 and c4)
print(f"VERDICT GELÉ : {'PASS' if verdict else 'FAIL — hypothèse réfutée'} (budget = 1 expérience, STOP)")

# ── BLOC STATS mensuel + garde-fou composé-des-mois vs somme simple ──
print("\n═══ BLOC STATS MENSUEL (poolé forward, 1x, 0 liq par construction) ═══")
order = np.argsort(ts0, kind='stable')
exit_ts = np.array([r[11] for r in recs])
import datetime as dtm
def mkey(t):
    d = dtm.datetime.fromtimestamp(t / 1000, dtm.timezone.utc)
    return f"{d.year}-{d.month:02d}"
mk = np.array([mkey(t) for t in ts0])
cum = 1.0
peak = 1.0
dd_max = 0.0
eq_curve = []
for i in order:                       # courbe composée séquentielle (ordre des entrées)
    cum *= (1.0 + ret24[i])
    eq_curve.append(cum)
    peak = max(peak, cum)
    dd_max = max(dd_max, (peak - cum) / peak)
eq_curve = np.array(eq_curve)
tot_comp = cum
tot_sum = ret24.mean() * len(ret24)
span_d = (ts0.max() - ts0.min()) / 86_400_000
roi_ann = (tot_comp - 1.0) / span_d * 365 * 100
print(f"{'mois':8s} {'split':6s} {'n':>6s} {'WR%':>6s} {'somme%':>9s} {'composé%':>10s}")
months = sorted(set(mk))
for m in months:
    msk = mk == m
    for sp, nm in ((0, 'TRAIN'), (1, 'VAL')):
        mm = msk & (split == sp)
        if mm.sum() == 0:
            continue
        x = ret24[mm]
        c = np.prod(1.0 + x)
        print(f"{m:8s} {nm:6s} {len(x):6d} {(x>0).mean()*100:6.1f} {x.sum()*100:+9.2f} {(c-1)*100:+10.2f}")
mrec = {}
for m in months:
    x = ret24[mk == m]
    mrec[m] = (np.prod(1.0 + x) - 1) * 100
best = max(mrec, key=mrec.get)
worst = min(mrec, key=mrec.get)
neg = sum(1 for v in mrec.values() if v < 0)
print(f"GLOBAL: somme simple {tot_sum*100:+.1f} % | composé {((tot_comp-1))*100:+.1f} % en {span_d:.0f} j "
      f"(≈ {roi_ann:+.0f} %/an linéarisé) | DD max séquentiel {dd_max*100:.1f} % | 0 liq")
print(f"Record mois {best} {mrec[best]:+.1f} % | pire mois {worst} {mrec[worst]:+.1f} % | mois négatifs {neg}/{len(mrec)}")

# garde-fou wallet non-chevauchant (1 position à la fois, premier événement fait foi)
for sp, nm in ((0, 'TRAIN'), (1, 'VAL')):
    last = -1.0
    keep = []
    for i in order[split[order] == sp]:
        if ts0[i] >= last:
            keep.append(i)
            last = exit_ts[i]
    x = ret24[np.array(keep, dtype=np.int64)] if keep else np.array([])
    if len(x) == 0:
        print(f"  Wallet non-chevauchant {nm}: 0 trade")
        continue
    c = np.prod(1.0 + x)
    peak, dd = 1.0, 0.0
    e = 1.0
    for v in 1.0 + x:
        e *= v
        peak = max(peak, e)
        dd = max(dd, (peak - e) / peak)
    print(f"  Wallet non-chevauchant {nm}: n={len(x)} composé {(c-1)*100:+.1f} % WR {(x>0).mean()*100:.1f} % DD {dd*100:.1f} %")
print("\nEXÉCUTION UNIQUE TERMINÉE")
