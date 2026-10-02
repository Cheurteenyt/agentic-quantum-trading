# INV-F — « LA CO-DÉFORMATION » (one-shot, protocole gelé docs/38 freeze-2026-10-02)
# ARCHIVÉ (02/10/2026) — INV-F : SOUS-PUISSENT, budget consommé, STOP (docs/38)
# Pré-enregistrement : reports/aster/inv-f-codeformation-2026-10.md
# Seal sha256 (gelé AVANT exécution) : 8e6fa1bf0e64b5e073c12e8bb86355b451da24ab4493b3030f58f6a5c2ded665
# Exécution UNIQUE — aucun re-run de variante autorisé.
import sqlite3
import numpy as np
import datetime as dt

DB = "data/warehouse/klines.db"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
ETALON_BPS = 12.2          # aller/retour taker (étalon gelé)
W = 72                     # fenêtre stats V et C (gelée)
HOR = 72                   # horizon de doublage (gelé)
FWD_LO, FWD_HI = 168, 335  # amplitude forward 7-14 j : barres t+168..t+335 (gelé)
MIN_EVT_TRAIN = 30         # n_train >= 30 sinon SOUS-PUISSENT (gelé)

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
closes, ts_ref = {}, None
for s in SYMS:
    rows = con.execute(
        "SELECT open_time, close FROM klines WHERE symbol=? AND interval='1h' ORDER BY open_time",
        (s,),
    ).fetchall()
    closes[s] = {t: c for t, c in rows}
    if ts_ref is None or len(rows) < len(ts_ref):
        ts_ref = rows
con.close()

# Heures communes (gelé : intersection des 6)
common = sorted(set(ts[0] for ts in ts_ref).intersection(*(set(closes[s]) for s in SYMS)))
ts = np.array(common, dtype=np.int64)
P = np.array([[closes[s][t] for s in SYMS] for t in common], dtype=float)  # (n_hours, 6)
n = len(ts)
assert P.shape == (n, 6)
print(f"Panel : {n} heures communes, {dt.datetime.fromtimestamp(ts[0]/1000, dt.UTC)} -> "
      f"{dt.datetime.fromtimestamp(ts[-1]/1000, dt.UTC)}")
print("Leçon ts_ms : open_time en MILLISECONDES, grille horaire exacte (vérifié en pré-enregistrement)")

# Split 60/40 chrono GLOBAL (gelé)
T_split = float(np.percentile(ts, 60))
i_split = int(np.searchsorted(ts, T_split, side="left"))
print(f"T_split = {T_split:.0f} = {dt.datetime.fromtimestamp(T_split/1000, dt.UTC)} | "
      f"TRAIN {i_split} h / VAL {n - i_split} h")

# ret24_i(t) = close(t)/close(t-24) - 1  (gelé)
R24 = np.full((n, 6), np.nan)
R24[24:, :] = P[24:, :] / P[:-24, :] - 1.0

# sigma_i(t) ddof=1 sur les 72 dernières ret24 ; V_t = moyenne des 6 sigma ; C_t = moyenne 15 corrs (gelé)
V = np.full(n, np.nan)
C = np.full(n, np.nan)
for t in range(2 * 24 + W - 1, n):  # ret24 défini dès 24 ; 72 valeurs -> t >= 24 + W - 1 = 95
    win = R24[t - W + 1: t + 1, :]
    if not np.isfinite(win).all():
        continue
    V[t] = win.std(axis=0, ddof=1).mean()
    cm = np.corrcoef(win, rowvar=False)
    iu = np.triu_indices(6, 1)
    C[t] = cm[iu].mean()
ok_vc = np.isfinite(V) & np.isfinite(C)
first_ok = int(np.argmax(ok_vc))
print(f"V/C définis à partir de l'index {first_ok} ({dt.datetime.fromtimestamp(ts[first_ok]/1000, dt.UTC)}), "
      f"{ok_vc.sum()} heures")

# q80 de C sur TRAIN SEULEMENT (gelé)
q80 = float(np.quantile(C[first_ok:i_split][ok_vc[first_ok:i_split]], 0.80))
print(f"q80(C) TRAIN = {q80:.6f}  (n = {ok_vc[first_ok:i_split].sum()} heures)")

# Événement à t (gelé) : (1) V_t >= 2*min(V_{t-1..t-72}) ; (2) traversée : C_t > q80 ET C_{t-1} <= q80
is_evt = np.zeros(n, dtype=bool)
J = np.full(n, np.nan)  # ampleur du saut
for t in range(first_ok + HOR, n):
    if not (ok_vc[t] and ok_vc[t - 1]):
        continue
    v_min = V[t - HOR: t].min()
    if not np.isfinite(v_min) or v_min <= 0:
        continue
    J[t] = V[t] / v_min
    if V[t] >= 2.0 * v_min and C[t] > q80 and C[t - 1] <= q80:
        is_evt[t] = True

# Amplitude forward 7-14 j : moyenne des |ret 1h| sur barres t+168..t+335 (gelé)
A = np.full(n, np.nan)
ret1 = np.full(n, np.nan)
ret1[1:] = P[1:, :].mean(axis=1) / P[:-1, :].mean(axis=1) - 1.0  # ret 1h du pack (prix moyen) pour A
for t in range(n):
    if t + FWD_HI < n:
        seg = ret1[t + FWD_LO: t + FWD_HI + 1]
        if np.isfinite(seg).all():
            A[t] = np.abs(seg).mean() * 1e4  # bps
meas = np.isfinite(A)
print(f"Amplitude A_t mesurable sur {meas.sum()} heures "
      f"(TRAIN {meas[:i_split].sum()} / VAL {meas[i_split:].sum()})")

evt_idx = np.where(is_evt)[0]
evt_meas = evt_idx[meas[evt_idx]]
n_tr_evt = int((evt_meas < i_split).sum())
n_va_evt = int((evt_meas >= i_split).sum())
print(f"\nÉvénements (traversées) : TRAIN {n_tr_evt} mesurables / VAL {n_va_evt} mesurables "
      f"(bruts : TRAIN {int((is_evt[:i_split]).sum())}, VAL {int((is_evt[i_split:]).sum())})")
# épisodes = séparés par >= 24 h sans événement
eps = 1 + int((np.diff(evt_idx) >= 24).sum()) if len(evt_idx) else 0
print(f"Épisodes distincts (gap >= 24 h) : {eps}")

# Datation des événements
print("\nDatation des événements mesurables :")
for i in evt_meas:
    sp = "TRAIN" if i < i_split else "VAL"
    print(f"  {dt.datetime.fromtimestamp(ts[i]/1000, dt.UTC)} {sp}  V={V[i]:.5f} C={C[i]:.4f} J={J[i]:.2f} A={A[i]:.1f} bps")

# Δ|fwd| par split (gelé) : med(A|evt) - med(A|sans événement), baseline = heures mesurables non-événements
def split_stats(lo, hi, name):
    m = meas[lo:hi]
    e = is_evt[lo:hi] & m
    b = m & ~is_evt[lo:hi]
    Ae, Ab = A[lo:hi][e], A[lo:hi][b]
    if len(Ae) == 0 or len(Ab) == 0:
        return None
    d = float(np.median(Ae) - np.median(Ab))
    print(f"{name}: n_evt={len(Ae)} medA_evt={np.median(Ae):.1f} | n_sans={len(Ab)} "
          f"medA_sans={np.median(Ab):.1f} | Delta={d:+.1f} bps (étalon {ETALON_BPS})")
    return d, np.median(Ae), np.median(Ab), len(Ae), len(Ab)

print("\n=== CRITÈRES (gelés) ===")
crit = {}
r_tr = split_stats(0, i_split, "TRAIN")
r_va = split_stats(i_split, n, "VAL  ")
crit["n_train>=30"] = n_tr_evt >= MIN_EVT_TRAIN
crit["Delta_train>etalon"] = r_tr is not None and r_tr[0] > ETALON_BPS
crit["Delta_val>0"] = r_va is not None and r_va[0] > 0
crit["controle_inverse_TRAIN"] = r_tr is not None and r_tr[2] < r_tr[1]
crit["controle_inverse_VAL"] = r_va is not None and r_va[2] < r_va[1]

# Gradient terciles de J sur TRAIN (gelé) : med(A) non décroissante, >= 5/tercile
ev_tr = evt_meas[evt_meas < i_split]
if len(ev_tr) >= 3:
    jt = J[ev_tr]
    t1, t2 = np.quantile(jt, [1 / 3, 2 / 3])
    terc = [ev_tr[jt <= t1], ev_tr[(jt > t1) & (jt <= t2)], ev_tr[jt > t2]]
    meds = [(len(s), float(np.median(A[s])) if len(s) else np.nan) for s in terc]
    print(f"Gradient TRAIN : T1(n={meds[0][0]}, med={meds[0][1]:.1f}) T2(n={meds[1][0]}, med={meds[1][1]:.1f}) "
          f"T3(n={meds[2][0]}, med={meds[2][1]:.1f}) [bornes J: {t1:.2f}/{t2:.2f}]")
    crit["gradient_monotone"] = (meds[0][0] >= 5 and meds[1][0] >= 5 and meds[2][0] >= 5
                                 and meds[0][1] <= meds[1][1] <= meds[2][1])
else:
    crit["gradient_monotone"] = False
    print("Gradient TRAIN : non évaluable (< 3 événements)")

# VAL descriptif (jamais un critère)
ev_va = evt_meas[evt_meas >= i_split]
if len(ev_va) >= 2:
    jv = J[ev_va]
    t1v, t2v = np.quantile(jv, [1 / 3, 2 / 3])
    print("Gradient VAL (descriptif) : ", end="")
    for nm, sel in [("T1", ev_va[jv <= t1v]), ("T2", ev_va[(jv > t1v) & (jv <= t2v)]), ("T3", ev_va[jv > t2v])]:
        print(f"{nm}(n={len(sel)}, med={np.median(A[sel]):.1f}) " if len(sel) else f"{nm}(n=0) ", end="")
    print()

# BLOC STATS mensuel (gelé)
print("\n=== BLOC STATS mensuel ===")
print("mois | split | n_evt | n_mesurables | medA_evt | medA_sans | Delta")
months = {}
for i in range(first_ok, n):
    if not meas[i]:
        continue
    mo = dt.datetime.fromtimestamp(ts[i]/1000, dt.UTC).strftime("%Y-%m")
    sp = "TRAIN" if i < i_split else "VAL"
    months.setdefault((mo, sp), {"e": [], "b": []})
    (months[(mo, sp)]["e"] if is_evt[i] else months[(mo, sp)]["b"]).append(A[i])
for (mo, sp), d in sorted(months.items()):
    de, db = d["e"], d["b"]
    me = f"{np.median(de):.1f}" if de else "—"
    mb = f"{np.median(db):.1f}" if db else "—"
    dd = f"{np.median(de) - np.median(db):+.1f}" if de and db else "—"
    print(f"{mo} | {sp} | {len(de)} | {len(de)+len(db)} | {me} | {mb} | {dd}")

# CONTEXTE SENS=0 (descriptif, jamais un signal)
print("\n=== CONTEXTE SENS=0 (descriptif) ===")
for lo, hi, nm in [(0, i_split, "TRAIN"), (i_split, n, "VAL")]:
    ev = [i for i in evt_meas if lo <= i < hi]
    if ev:
        drift = [ (P[i + FWD_HI][0] / P[i + FWD_LO][0] - 1) * 100 for i in ev ]  # BTC seulement, descriptif
        print(f"{nm}: dérive forward 7-14j des événements (BTC, t+168->t+335) médiane "
              f"{np.median(drift):+.2f} % (n={len(ev)})")

print("\n=== VERDICT MÉCANIQUE ===")
if not crit["n_train>=30"]:
    print(f"SOUS-PUISSENT : n_train = {n_tr_evt} < {MIN_EVT_TRAIN} (gelé) — aucun PASS possible, "
          "aucun relâchement autorisé")
else:
    for k, v in crit.items():
        print(f"{'OK ' if v else 'FAUX'} {k}")
    print("PASS" if all(crit.values()) else "FAIL — hypothèse réfutée")
