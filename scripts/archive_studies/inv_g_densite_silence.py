#!/usr/bin/env python3
# ARCHIVÉ (02/10/2026) — INV-G : FAIL hypothèse réfutée (docs/38, budget consommé)
# INV-G — « LA DENSITÉ DE SILENCE » (pré-enregistré, exécution unique 02/10/2026)
# Gouvernance : docs/38-gouvernance-recherche.md, tag freeze-2026-10-02.
# Registre : research/registry.yaml vérifié (aucune expérience « silence » /
# retours nuls antérieure) — expérience GÉNUILEMENT nouvelle.
# Adjacence déclarée : T20 = densité de PRINTS du tape (BTC/ETH, 90 j, descriptif,
# reports/aster_orderflow_regimes.md) — ici : densité de RETOURS NULS 1h par
# symbole sur klines profonds, prédiction forward de MAGNITUDE jamais formulée.
# Hypothèse (MAGNITUDE, PAS DIRECTION — leçon OI vague 10) :
#   S_t = fraction des 72 dernières bougies 1h avec |ret| < 0,05 % (heures mortes).
#   Événement = S_t >= q90 TRAIN (un seul seuil, zéro grille).
#   L'amplitude forward 48-96h (somme des |ret|) des événements dépasse la
#   médiane inconditionnelle de plus que l'étalon 12,2 bps A/R taker.
# SENS = 0 : toute séparation directionnelle = CONTEXTE descriptif.
# Protocole : split 60/40 chrono GLOBAL, pas de trade (conditionneur de taille),
# n_train >= 100 sinon SOUS-PUISSENT, BLOC STATS mensuel.
# PASS (4 critères gelés, écrits AVANT dans reports/aster/inv-g-densite-silence-2026-10.md) :
#   1. Δ|fwd| TRAIN > 12,2 bps   2. VAL > 0 même signe
#   3. gradient quintiles S_t non décroissant (TRAIN)
#   4. contrôle inverse (S_t <= q10) battu TRAIN ET VAL.
# FAIL = tout le reste → « FAIL — hypothèse réfutée », STOP (budget = 1 expérience).
# DB : data/warehouse/klines.db en LECTURE SEULE (mode=ro). Aucune écriture.

import sqlite3
import datetime
import numpy as np

DB = 'file:data/warehouse/klines.db?mode=ro'
H = 3_600_000           # 1 h en ms (leçon ts_ms : open_time en MILLISECONDES)
DEAD_BPS = 5.0          # heure « morte » : |ret| < 0,05 % = 5 bps
LOOKBACK = 72           # fenêtre S_t
FWD0, FWD1 = 48, 96     # amplitude forward [t+48h ; t+95h]
SPLIT_Q = 60            # split 60/40 chrono global
EVENT_Q = 90            # un seul seuil
ETALON_BPS = 12.2       # aller/retour taker
MIN_TRAIN = 100

con = sqlite3.connect(DB, uri=True)
cur = con.cursor()

# ── Univers figé AVANT toute statistique de résultat ──
# Règle unique : symboles de `klines` interval='1h' avec >= 2000 barres (≈ 83 j) —
# assez profond pour remplir la fenêtre roulante 72 h + la fenêtre forward.
rows = cur.execute("""
    SELECT symbol, COUNT(*) FROM klines WHERE interval='1h'
    GROUP BY symbol HAVING COUNT(*) >= 2000 ORDER BY symbol
""").fetchall()
symbols = [r[0] for r in rows]
print(f"UNIVERSE n={len(symbols)} symboles (>= 2000 barres 1h)")
for s, n in rows:
    t0, t1 = cur.execute(
        "SELECT MIN(open_time), MAX(open_time) FROM klines WHERE interval='1h' AND symbol=?",
        (s,)).fetchone()
    d0 = datetime.datetime.utcfromtimestamp(t0 / 1000).strftime('%Y-%m-%d')
    d1 = datetime.datetime.utcfromtimestamp(t1 / 1000).strftime('%Y-%m-%d')
    print(f"  {s:16s} {n:6d} barres  {d0} -> {d1}")

# ── Contrôles d'intégrité (leçon ts_ms, grille, doublons) ──
tmin = cur.execute("SELECT MIN(open_time) FROM klines WHERE interval='1h'").fetchone()[0]
assert tmin > 1e12, "open_time n'est PAS en millisecondes — STOP (leçon ts_ms)"
ndup = cur.execute("""SELECT COUNT(*) FROM (
    SELECT symbol, open_time, COUNT(*) c FROM klines WHERE interval='1h'
    GROUP BY 1,2 HAVING c>1)""").fetchone()[0]
assert ndup == 0, f"{ndup} doublons (symbol, open_time) — STOP"
nbad = cur.execute(
    "SELECT COUNT(*) FROM klines WHERE interval='1h' AND (open_time % 3600000) != 0"
).fetchone()[0]
assert nbad == 0, f"{nbad} open_time hors grille 1h — STOP"

# ── Chargement ──
data = {}
for s in symbols:
    arr = cur.execute(
        "SELECT open_time, close FROM klines WHERE interval='1h' AND symbol=? ORDER BY open_time",
        (s,)).fetchall()
    data[s] = (np.array([a[0] for a in arr], dtype=np.int64),
               np.array([a[1] for a in arr], dtype=np.float64))
con.close()

# ── Split 60/40 chrono GLOBAL : percentile 60 des open_time uniques poolés ──
all_t = np.unique(np.concatenate([data[s][0] for s in symbols]))
T_SPLIT = np.percentile(all_t, SPLIT_Q)  # non arrondi, règle gelée
print(f"\nT_SPLIT = {T_SPLIT:.0f} ms = "
      f"{datetime.datetime.utcfromtimestamp(T_SPLIT/1000).strftime('%Y-%m-%d %H:%M UTC')}"
      f"  ({len(all_t)} timestamps uniques poolés)")

# ── Construction S_t / A_t par symbole (causal, sans fuite) ──
# S_t mesurable ssi 168 barres contiguës t-72h..t+95h présentes (base ret S = t-72h,
# rets S sur t-71h..t, base ret A = t+47h, rets A sur t+48h..t+95h).
recs = []  # (t, S, A, D, split, symbol)
n_excl = 0
for s in symbols:
    ts, c = data[s]
    n = len(ts)
    for i in range(LOOKBACK, n - FWD1 + 1):
        t = ts[i]
        if (ts[i - LOOKBACK] != t - LOOKBACK * H or ts[i + FWD1 - 1] != t + (FWD1 - 1) * H
                or i + FWD1 - 1 - (i - LOOKBACK) + 1 != LOOKBACK + FWD1):
            n_excl += 1
            continue
        # (attribution symbole porte par l'enregistrement lui-même)
        r_s = c[i - 70:i + 1] / c[i - 71:i] - 1.0
        S = float((np.abs(r_s) < DEAD_BPS / 1e4).mean())
        r_a = c[i + FWD0:i + FWD1] / c[i + FWD0 - 1:i + FWD1 - 1] - 1.0
        A = float(np.abs(r_a).sum() * 1e4)          # bps
        D = float(c[i + FWD1 - 1] / c[i + FWD0 - 1] - 1.0)  # dérive forward (SENS=0)
        split = 'TRAIN' if t < T_SPLIT else 'VAL'
        recs.append((t, S, A, D, split, s))

t_arr = np.array([r[0] for r in recs], dtype=np.int64)
S_arr = np.array([r[1] for r in recs])
A_arr = np.array([r[2] for r in recs])
D_arr = np.array([r[3] for r in recs])
sp_arr = np.array([r[4] for r in recs])
sym_arr = np.array([r[5] for r in recs])
is_tr = sp_arr == 'TRAIN'
print(f"\nPERIODES mesurables (S et A) : {len(recs)}  (exclues trous: {n_excl})")
print(f"  TRAIN {is_tr.sum()}  VAL {(~is_tr).sum()}")

S_tr = S_arr[is_tr]
q90 = float(np.quantile(S_tr, EVENT_Q / 100))
q10 = float(np.quantile(S_tr, 10 / 100))
edges = np.quantile(S_tr, [0.2, 0.4, 0.6, 0.8])
print(f"\nSEUIL (TRAIN only) : q90(S_t) = {q90:.6f} = {q90*72:.1f}/72 heures mortes")
print(f"q10(S_t) = {q10:.6f} ; quintiles TRAIN = {np.round(edges, 6).tolist()}")

ev = (S_arr >= q90)
print(f"EVENTS (S_t >= q90) : TRAIN {int((ev & is_tr).sum())}  VAL {int((ev & ~is_tr).sum())}")
print(f"taux d'evenement global : {ev.mean()*100:.2f} %")

# ── Statistiques principales ──
def med(x):
    return float(np.median(x)) if len(x) else float('nan')

print("\n=== DELTA AMPLITUDE (bps) ===")
res = {}
for split, mask_sp in (('TRAIN', is_tr), ('VAL', ~is_tr)):
    base = mask_sp
    evt = ev & mask_sp
    low = (S_arr <= q10) & mask_sp
    mA_e, mA_a, mA_l = med(A_arr[evt]), med(A_arr[base]), med(A_arr[low])
    d = mA_e - mA_a
    res[split] = dict(n_all=int(base.sum()), n_evt=int(evt.sum()), n_low=int(low.sum()),
                      medA_evt=mA_e, medA_all=mA_a, medA_low=mA_l, delta=d,
                      medD_evt=med(D_arr[evt]), medD_all=med(D_arr[base]))
    print(f"{split}: n_base={int(base.sum())} n_evt={int(evt.sum())} n_low={int(low.sum())}")
    print(f"  medA_evt={mA_e:.1f}  medA_all={mA_a:.1f}  DELTA={d:+.1f} bps (etalon {ETALON_BPS})")
    print(f"  controle inverse S_t<=q10 : medA_low={mA_l:.1f}  (battu: {mA_l < mA_e})")
    print(f"  contexte SENS=0 (descriptif, non actionnable) : medD_evt={res[split]['medD_evt']*100:+.3f} %"
          f"  medD_all={res[split]['medD_all']*100:+.3f} %")

# ── Gradient quintiles S_t ──
print("\n=== GRADIENT QUINTILES S_t (bornes TRAIN, VAL descriptif) ===")
qi = np.searchsorted(edges, S_arr, side='right')  # 0..4
mono = True
prev = None
for q in range(5):
    m = (qi == q) & is_tr
    mv = (qi == q) & ~is_tr
    mtr = med(A_arr[m])
    if prev is not None and mtr < prev - 1e-9:
        mono = False
    prev = mtr
    print(f"  Q{q+1} TRAIN n={int(m.sum()):6d} medA={mtr:8.1f} | VAL n={int(mv.sum()):6d} medA={med(A_arr[mv]):8.1f}")
print(f"monotone TRAIN (Q1<=Q2<=Q3<=Q4<=Q5) : {mono}")

# ── Concentration par symbole (descriptif) ──
print("\n=== EVENTS par symbole (descriptif) ===")
from collections import Counter
for split in ('TRAIN', 'VAL'):
    m = ev & (is_tr if split == 'TRAIN' else ~is_tr)
    cnt = Counter(sym_arr[m])
    top = ', '.join(f"{k} {v}" for k, v in cnt.most_common(8))
    print(f"  {split}: top — {top}")

# ── BLOC STATS mensuel ──
print("\n=== BLOC STATS MENSUEL (medA en bps ; 0 liq par construction) ===")
print("| Mois | Split | n evts | n toutes | medA evts | medA toutes | Delta |")
months = np.array([datetime.datetime.utcfromtimestamp(int(t) / 1000).strftime('%Y-%m')
                   for t in t_arr])
for mo in sorted(set(months.tolist())):
    m = months == mo
    split = 'TRAIN' if is_tr[m][0] else 'VAL'
    e = ev[m]
    a = A_arr[m]
    d = (med(a[e]) - med(a)) if e.any() else float('nan')
    print(f"| {mo} | {split} | {int(e.sum())} | {int(m.sum())} | "
          f"{med(a[e]) if e.any() else float('nan'):.1f} | {med(a):.1f} | "
          f"{d:+.1f} |" if e.any() else
          f"| {mo} | {split} | 0 | {int(m.sum())} | — | {med(a):.1f} | — |")

# ── Verdict (critères gelés) ──
print("\n=== VERDICT ===")
n_tr = res['TRAIN']['n_evt']
c1 = res['TRAIN']['delta'] > ETALON_BPS
c2 = res['VAL']['delta'] > 0 and np.sign(res['VAL']['delta']) == np.sign(res['TRAIN']['delta'])
c3 = mono
c4 = (res['TRAIN']['medA_low'] < res['TRAIN']['medA_evt']
      and res['VAL']['medA_low'] < res['VAL']['medA_evt'])
print(f"n_train = {n_tr} (>= {MIN_TRAIN} : {n_tr >= MIN_TRAIN})"
      f"{'' if n_tr >= MIN_TRAIN else '  → SOUS-PUISSENT déclaré'}")
print(f"C1 TRAIN delta > etalon 12,2 : {c1} ({res['TRAIN']['delta']:+.1f})")
print(f"C2 VAL delta > 0 meme signe  : {c2} ({res['VAL']['delta']:+.1f})")
print(f"C3 gradient monotone TRAIN   : {c3}")
print(f"C4 controle inverse battu TR&VAL : {c4}")
if n_tr < MIN_TRAIN:
    print("VERDICT : SOUS-PUISSENT (échec de puissance ≠ réfutation) — gravé, STOP")
elif c1 and c2 and c3 and c4:
    print("VERDICT : PASS → CONTEXTE/CANDIDATE gate de sizing (jamais un signal autonome)")
else:
    print("VERDICT : FAIL — hypothèse réfutée (gravé, STOP, budget = 1 expérience)")
