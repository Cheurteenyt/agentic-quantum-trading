#!/usr/bin/env python3
# ARCHIVÉ (02/10/2026) — INV-E : FAIL hypothèse réfutée (docs/38, budget consommé)
# INV-E — « LE RYTHME DU FUNDING » — one-shot (pré-enregistré 2026-10-02)
# Gouvernance : docs/38-gouvernance-recherche.md, tag freeze-2026-10-02.
# Pré-enregistrement : reports/aster/inv-e-rythme-funding-2026-10.md
# Seal sha256 du bloc pré-enregistrement (gelé avant exécution) :
#   501c47979d2f833caecb2b39899b9bcc38634604de8eaa87aa5106b31abb2d5b
# Hypothèse : MAGNITUDE, PAS DIRECTION — après une séquence de funding
# exceptionnellement longue (R_t >= q90 TRAIN), l'amplitude forward 48-96h
# (somme des |ret| 1h) est supérieure à la médiane. SENS = 0 (conditionneur
# de taille, jamais un signal). Budget = 1 expérience. FAIL = STOP.
#
# EXÉCUTION UNIQUE — aucune variante autorisée après coup.

import sqlite3
import numpy as np
from datetime import datetime, timezone

DB = "file:data/warehouse/klines.db?mode=ro"
H = 3_600_000            # 1 heure en ms (leçon ts_ms : tout est en MILLISECONDES)
DAY = 86_400_000
ETALON_BPS = 12.2        # aller/retour taker
Q_EVENT, Q_CTRL = 0.90, 0.10

def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")

con = sqlite3.connect(DB, uri=True)
cur = con.cursor()

# ── Univers : intervalle médian de funding = 8h ET >= 90 observations ─────────
universe = []
for (sym,) in cur.execute("SELECT DISTINCT symbol FROM funding_history").fetchall():
    ts = [r[0] for r in cur.execute(
        "SELECT funding_time FROM funding_history WHERE symbol=? ORDER BY funding_time", (sym,))]
    if len(ts) < 90:
        continue
    gaps = np.diff(np.array(ts))
    if not (7.5 * H <= np.median(gaps) <= 8.5 * H):
        continue
    universe.append(sym)
universe.sort()
with_kl = [s for s in universe if cur.execute(
    "SELECT 1 FROM klines WHERE symbol=? AND interval='1h' LIMIT 1", (s,)).fetchone()]
print(f"UNIVERSE regle 8h+90obs ({len(universe)}): {', '.join(universe)}")
print(f"  mesurables (klines 1h presents) ({len(with_kl)}): {', '.join(with_kl)}")
print(f"  sans klines 1h (0 periode mesurable) ({len(universe)-len(with_kl)}): "
      f"{', '.join(s for s in universe if s not in with_kl)}")

# ── Séries de funding : signe (+1/-1/0) et run-length causal ──────────────────
series = {}   # sym -> list[(t, sign, R)] signe!=0 ; zeros cassent
all_ts = set()
for sym in universe:
    rows = cur.execute(
        "SELECT funding_time, rate FROM funding_history WHERE symbol=? ORDER BY funding_time",
        (sym,)).fetchall()
    out, run_sign, run_len = [], 0, 0
    for t, rate in rows:
        all_ts.add(t)
        s = 1 if rate > 0 else (-1 if rate < 0 else 0)
        if s == 0:
            run_sign, run_len = 0, 0
            continue
        if s == run_sign:
            run_len += 1
        else:
            run_sign, run_len = s, 1
        out.append((t, s, run_len))
    series[sym] = out

# ── Split 60/40 chrono GLOBAL ─────────────────────────────────────────────────
uniq = np.array(sorted(all_ts))
t_split = float(np.percentile(uniq, 60))
print(f"SPLIT GLOBAL: T_split = {utc(t_split)} UTC ({len(uniq)} ts uniques poolés)")

# ── Klines 1h des symboles de l'univers ───────────────────────────────────────
closes = {}
for sym in universe:
    rows = cur.execute(
        "SELECT open_time, close FROM klines WHERE symbol=? AND interval='1h' ORDER BY open_time",
        (sym,)).fetchall()
    closes[sym] = {int(t): float(c) for t, c in rows}

def measure(sym, t):
    """A_t (bps) = somme des 48 |ret| 1h sur [t+48h, t+95h], base t+47h.
    Retourne (amplitude_bps, ret_dir) ou None si couverture incomplète."""
    cl = closes[sym]
    need = [t + k * H for k in range(47, 96)]        # closes t+47h .. t+95h
    if any(x not in cl for x in need):
        return None
    amp = sum(abs(cl[t + k * H] / cl[t + (k - 1) * H] - 1.0) for k in range(48, 96))
    ret_dir = cl[t + 95 * H] / cl[t + 47 * H] - 1.0
    return amp * 1e4, ret_dir

# ── Mesure de toutes les périodes signe!=0 (événements + base) ────────────────
# Base = TOUTES les périodes mesurables du split (signe quelconque, y compris 0).
recs = []            # (sym, t, split, sign, R, amp_bps, ret_dir)
excl_no_kl = 0
zero_periods = 0
for sym in universe:
    rows = cur.execute(
        "SELECT funding_time, rate FROM funding_history WHERE symbol=? ORDER BY funding_time",
        (sym,)).fetchall()
    rl = {t: (s, r) for t, s, r in series[sym]}
    for t, rate in rows:
        split = "TRAIN" if t < t_split else "VAL"
        s, R = rl.get(t, (0, 0))
        if s == 0:
            zero_periods += 1
            m = measure(sym, t)
            if m is None:
                excl_no_kl += 1
                continue
            recs.append((sym, t, split, 0, 0, m[0], m[1]))
            continue
        m = measure(sym, t)
        if m is None:
            excl_no_kl += 1
            continue
        recs.append((sym, t, split, s, R, m[0], m[1]))

n_meas = len(recs)
print(f"PERIODES: mesurables {n_meas} | exclues (couverture 1h) {excl_no_kl} | signe 0 {zero_periods}")

# ── Seuil unique q90 (TRAIN, signe!=0, poolé) + q10 du contrôle ───────────────
R_train = np.array([r[4] for r in recs if r[2] == "TRAIN" and r[3] != 0], dtype=float)
q90 = float(np.quantile(R_train, Q_EVENT))
q10 = float(np.quantile(R_train, Q_CTRL))
print(f"R TRAIN (signe!=0): n={len(R_train)} | q10={q10:g} q50={np.median(R_train):g} "
      f"q90={q90:g} max={R_train.max():g}")
print(f"R VAL max (descriptif): "
      f"{max((r[4] for r in recs if r[2]=='VAL' and r[3]!=0), default=0):g}")

def med(xs):
    return float(np.median(xs)) if len(xs) else float("nan")

def block(name, rows_):
    ev = [r for r in rows_ if r[3] != 0 and r[4] >= q90]
    al = rows_
    m_ev, m_al = med([r[5] for r in ev]), med([r[5] for r in al])
    print(f"{name}: n_evts={len(ev)} n_toutes={len(al)} | medA_evts={m_ev:.1f} bps "
          f"medA_toutes={m_al:.1f} bps | Delta={m_ev - m_al:+.1f} bps")
    return ev, al, m_ev, m_al

print("\n== CRITERE 1+2 : Delta |fwd| (evenements vs mediane inconditionnelle) ==")
ev_tr, al_tr, m_ev_tr, m_al_tr = block("TRAIN", [r for r in recs if r[2] == "TRAIN"])
ev_va, al_va, m_ev_va, m_al_va = block("VAL  ", [r for r in recs if r[2] == "VAL"])
d_tr, d_va = m_ev_tr - m_al_tr, m_ev_va - m_al_va
c1 = d_tr > ETALON_BPS
c2 = d_va > 0

# ── Critère 3 : gradient quintiles de R (TRAIN, signe!=0) ─────────────────────
print("\n== CRITERE 3 : gradient quintiles de R (TRAIN, mediane A en bps) ==")
tr_nz = [r for r in recs if r[2] == "TRAIN" and r[3] != 0]
va_nz = [r for r in recs if r[2] == "VAL" and r[3] != 0]
edges = np.quantile([r[4] for r in tr_nz], [0.2, 0.4, 0.6, 0.8])
def quint(r):
    return int(np.searchsorted(edges, r[4], side="right"))
meds_tr = []
for qi in range(5):
    sub = [r[5] for r in tr_nz if quint(r) == qi]
    sub_va = [r[5] for r in va_nz if quint(r) == qi]
    print(f"  Q{qi+1} (R<={edges[qi]:g}" if qi < 4 else "  Q5 (R max)", end="")
    print(f") TRAIN n={len(sub)} medA={med(sub):.1f} | VAL n={len(sub_va)} medA={med(sub_va):.1f}")
    meds_tr.append(med(sub))
c3 = all(meds_tr[i] <= meds_tr[i + 1] + 1e-9 for i in range(4))
print(f"  monotone Q1<=..<=Q5 : {meds_tr[0]:.1f} <= {meds_tr[1]:.1f} <= {meds_tr[2]:.1f} "
      f"<= {meds_tr[3]:.1f} <= {meds_tr[4]:.1f} -> {c3}")

# ── Critère 4 : contrôle inverse (séquences courtes R <= q10) ─────────────────
print("\n== CRITERE 4 : controle inverse (R <= q10 train) vs evenements ==")
ctrl_tr = [r[5] for r in recs if r[2] == "TRAIN" and r[3] != 0 and r[4] <= q10]
ctrl_va = [r[5] for r in recs if r[2] == "VAL" and r[3] != 0 and r[4] <= q10]
m_ct_tr, m_ct_va = med(ctrl_tr), med(ctrl_va)
print(f"  TRAIN: n_ctrl={len(ctrl_tr)} medA_ctrl={m_ct_tr:.1f} vs medA_evts={m_ev_tr:.1f} "
      f"-> evts>ctrl: {m_ev_tr > m_ct_tr}")
print(f"  VAL  : n_ctrl={len(ctrl_va)} medA_ctrl={m_ct_va:.1f} vs medA_evts={m_ev_va:.1f} "
      f"-> evts>ctrl: {m_ev_va > m_ct_va}")
c4 = (m_ev_tr > m_ct_tr) and (m_ev_va > m_ct_va)

# ── SENS = 0 : descriptif directionnel, CONTEXTE uniquement ───────────────────
print("\n== CONTEXTE (SENS=0, non actionnable) : direction forward 48-96h par signe du run ==")
for split, ev in (("TRAIN", ev_tr), ("VAL", ev_va)):
    for s, lab in ((1, "run+"), (-1, "run-")):
        rd = [r[6] for r in ev if r[3] == s]
        print(f"  {split} {lab}: n={len(rd)} med_ret48-96={med(rd)*100:+.2f}% "
              f"WR={'-' if not rd else f'{100*sum(x>0 for x in rd)/len(rd):.0f}%'}")

# ── BLOC STATS mensuel ────────────────────────────────────────────────────────
print("\n== BLOC STATS MENSUEL (medA en bps) ==")
print("  mois | split | n_evts | n_toutes | medA_evts | medA_toutes | Delta")
months = {}
for r in recs:
    key = utc(r[1])[:7]
    months.setdefault(key, {"TRAIN": [], "VAL": []})[r[2]].append(r)
neg_months, worst, best = 0, 0.0, 0.0
for k in sorted(months):
    for sp in ("TRAIN", "VAL"):
        rows_ = months[k][sp]
        if not rows_:
            continue
        ev = [r for r in rows_ if r[3] != 0 and r[4] >= q90]
        m_ev, m_al = med([r[5] for r in ev]), med([r[5] for r in rows_])
        d = m_ev - m_al if ev else float("nan")
        print(f"  {k} | {sp} | {len(ev):5d} | {len(rows_):7d} | {m_ev:9.1f} | {m_al:9.1f} | {d:+7.1f}")

# ── Verdict ───────────────────────────────────────────────────────────────────
print("\n== VERDICT ==")
print(f"n_evts TRAIN={len(ev_tr)} (>=100 requis: {len(ev_tr) >= 100}) | "
      f"C1 Delta_train>{ETALON_BPS}: {d_tr:+.1f} bps -> {c1} | "
      f"C2 Delta_val>0: {d_va:+.1f} bps -> {c2}")
print(f"C3 gradient: {c3} | C4 controle inverse battu: {c4}")
if len(ev_tr) < 100:
    print("SOUS-PUISSANT — echec de puissance, ni PASS ni refutation")
elif c1 and c2 and c3 and c4:
    print("PASS -> CONTEXTE / CANDIDATE gate de sizing (jamais un signal autonome)")
else:
    print("FAIL — hypothese refutee. Budget consomme, STOP, aucune variante.")
con.close()
