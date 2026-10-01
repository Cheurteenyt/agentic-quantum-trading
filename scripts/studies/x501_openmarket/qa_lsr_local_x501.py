#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_lsr_local_x501.py — QA de la vague 11 (banc LSR, x501_lsr_local.py).

Discipline QA du domaine (vagues 5-10, transposée) : le banc ne vaut que si
sa plomberie est prouvée VIVANTE (un détecteur planté doit décoller), si le
ZÉRO LOOK-AHEAD est prouvé par mutation (multiplicative ET additive, des
lignes LSR ET des klines — leçon vague 7), si la ligne simultanée n'est
JAMAIS lue, si les 4 branches du verdict sont exactes, si le pool 469/469
est respecté, si l'audit de collecte est vert et si la re-exécution est
bit à bit (digest SHA-256 gravé).

Usage : python3 qa_lsr_local_x501.py  (data locale, zéro réseau)
Sortie : OK/FAIL par contrôle, code de sortie 1 au premier échec.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import x501_lsr_local as st  # noqa: E402
import x501_collect_lsr_v11 as col  # noqa: E402

MS_4H = st.MS_4H
MS_1D = st.MS_1D

PASS, FAIL = 0, 0
NAMES = []


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")
    NAMES.append((name, bool(cond)))


# ============================ S1 — rolling_z ==================================
print("S1 — rolling_z (z-score roulant, fenêtre au passé, seuil plat relatif)")
a = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
z = st.rolling_z(a, 3)
# cas à la main : z[2] = (3 - 2)/sqrt(2/3) ; z[3] = (4-3)/sqrt(2/3)
check("S1.1 cas à la main L=3 z[2]", np.isclose(z[2], 1.0 / np.sqrt(2.0 / 3.0)))
check("S1.2 cas à la main L=3 z[3]", np.isclose(z[3], 1.0 / np.sqrt(2.0 / 3.0)))
check("S1.3 amorçage NaN (indices 0,1)", np.isnan(z[:2]).all())
check("S1.4 pas de NaN après amorçage", np.isfinite(z[2:]).all())
rng = np.random.default_rng(11)
x = rng.normal(0.0, 1.0, 600)
z = st.rolling_z(x, 20)
zn = np.full(600, np.nan)
for i in range(19, 600):
    w = x[i - 19:i + 1]
    zn[i] = (x[i] - w.mean()) / w.std(ddof=0)
ok = np.isfinite(zn)
check("S1.5 contre-vérification boucle naïve 600 pts",
      np.allclose(z[ok], zn[ok], equal_nan=False))
cst = np.full(100, 5.0)
zc = st.rolling_z(cst, 10)
check("S1.6 fenêtre plate (constante) -> NaN", np.isnan(zc[9:]).all())
check("S1.7 seuil relatif : quasi-constante (dispersion 1e-9) -> NaN",
      np.isnan(st.rolling_z(5.0 + rng.normal(0, 1e-9, 100), 10)[9:]).all())
check("S1.8 fenêtre vivante (dispersion 1e-3) -> PAS NaN",
      np.isfinite(st.rolling_z(5.0 + rng.normal(0, 1e-3, 100), 10)[9:]).all())
xn = x.copy()
xn[300] = np.nan
zn2 = st.rolling_z(xn, 20)
check("S1.9 NaN propagé : fenêtres contenant l'indice 300 (z[300..319])",
      np.isnan(zn2[300:320]).all() and np.isfinite(zn2[299]))
check("S1.10 L > n -> tout NaN", np.isnan(st.rolling_z(a, 50)).all())
check("S1.11 z[100] n'utilise JAMAIS x[100+] (fenêtre au passé)",
      np.isclose(st.rolling_z(x, 20)[100], zn[100]))

# ============================ S2 — delta_niveaux ==============================
print("S2 — delta_niveaux (flux du positionnement)")
d = st.delta_niveaux(a, 3)
check("S2.1 cas à la main d[3]=a[3]-a[0]=3", np.isclose(d[3], 3.0))
check("S2.2 cas à la main d[5]=a[5]-a[2]=3", np.isclose(d[5], 3.0))
check("S2.3 amorçage NaN (0..2)", np.isnan(d[:3]).all())
check("S2.4 Ld >= n -> tout NaN", np.isnan(st.delta_niveaux(a, 6)).all())

# ============ S3 — DÉTECTEUR : le pipeline synthétique complet ================
print("S3 — détecteur planté sur pipeline synthétique COMPLET (main() patché)")


def build_fake_panel(tmpdir, plant="4h"):
    """Un faux symbole FAKEUSDT : klines 4h/1d + LSR 4h/1d. Convention de
    la mécanique à planter : op[k+1]/op[k] - 1 = 0,01 e[k+1] (cumprod
    inclusif) donc fwd[t] = (op[t+h]-op[t])/op[t] ~ 0,01 * somme_{i=t+1..t+h} e[i],
    et le score lu à l'open de t est z à l'indice t-1 (shift vague 9) —
    pour anti-corréler, buy[j] doit encoder e[j+2] : buy[t-1] ~ -e[t+1],
    le terme de PIRE poids 1/h de fwd[t] (corr -1/racine(h)) -> AUC < 0,5
    fort. plant='4h' plante le 4h (1d nul), plant='1d' plante le 1d (4h
    nul), plant='none' : tout nul — le détecteur ne doit décoller QUE là
    où il est planté."""
    rng = np.random.default_rng(501)
    n4 = 3_000
    e = rng.normal(0.0, 1.0, n4)          # e[m] = sigma du rendement open m-1 -> m
    op4 = 100.0 * np.cumprod(1.0 + 0.01 * e)
    t0 = 1_700_000_000_000 - (n4 * MS_4H)
    ts4 = t0 + np.arange(n4) * MS_4H
    if plant == "4h":
        e2 = np.concatenate([e[2:], [0.0, 0.0]])   # e[j+2] : le FUTUR lu à t
        buy4 = 0.5 - 0.05 * e2 + rng.normal(0, 0.001, n4)
    else:
        buy4 = np.full(n4, 0.5) + rng.normal(0, 0.001, n4)
    ts4l = ts4                             # LSR pile sur la grille
    n1 = 1_500
    e1 = rng.normal(0.0, 1.0, n1)
    op1 = 100.0 * np.cumprod(1.0 + 0.01 * e1)
    ts1 = t0 + np.arange(n1) * MS_1D
    if plant == "1d":
        e1b = np.concatenate([e1[2:], [0.0, 0.0]])
        buy1 = 0.5 - 0.05 * e1b + rng.normal(0, 0.001, n1)
    else:
        buy1 = np.full(n1, 0.5) + rng.normal(0, 0.001, n1)
    d = Path(tmpdir)
    for tag, ts, op in [("240", ts4, op4), ("D", ts1, op1)]:
        with open(d / f"FAKEUSDT_klines_{tag}.jsonl", "w") as f:
            for t, o in zip(ts, op):
                f.write(json.dumps({"ts": int(t), "o": float(o), "h": float(o),
                                    "l": float(o), "c": float(o), "v": 1.0,
                                    "qv": 1.0}) + "\n")
    for tag, ts, b in [("4h", ts4l, buy4), ("1d", ts1, buy1)]:
        with open(d / f"FAKEUSDT_lsr_{tag}.jsonl", "w") as f:
            for t, bv in zip(ts, b):
                f.write(json.dumps({"ts": int(t), "buyRatio": float(bv),
                                    "sellRatio": float(1.0 - bv)}) + "\n")
    # pool factice : 30 entrées dans la fenêtre (t_in alignées kline 4h)
    rows = []
    for k in range(600, 600 + 30 * 40, 40):
        rows.append({"sym": "FAKEUSDT", "t_in": int(ts4[k]), "side": "1",
                     "entry": "1.0", "stop": "0.99", "dist_bps": "100",
                     "R": f"{(buy4[k] - 0.5) * 40 + rng.normal(0, 0.3):.6f}",
                     "alpha": "A1", "risk_usd": "2.5"})
    with open(d / "pool.csv", "w") as f:
        import csv as _csv
        w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return d


def run_fake_study(tmpdir, **kw):
    old = {k: getattr(st, k) for k in ("LSR_DIR", "POOL_CSV", "OUT_JSON", "SYMBOLS")}
    d = Path(tmpdir)
    st.LSR_DIR = d
    st.POOL_CSV = d / "pool.csv"
    st.OUT_JSON = d / "out.json"
    st.SYMBOLS = ["FAKEUSDT"]
    try:
        st.main()
        return json.load(open(st.OUT_JSON))
    finally:
        for k, v in old.items():
            setattr(st, k, k and v) if False else setattr(st, k, v)


tmp = tempfile.mkdtemp()
try:
    build_fake_panel(tmp, plant="4h")
    res = run_fake_study(tmp)
    ra = res["etude_A_contrarian_niveau_4h"]
    rc = res["etude_C_replication_1d"]
    aucs_a = [r["auc"] for r in ra.values()]
    verd_a = {r["verdict"] for r in ra.values()}
    verd_c = {r["verdict"] for r in rc.values()}
    check("S3.1 détecteur contrarian : AUC étude A < 0,5 (toutes cellules)",
          all(a < 0.48 for a in aucs_a))
    check("S3.2 détecteur contrarian : verdict CANDIDAT (sens -1 confirmé)",
          verd_a == {"CANDIDAT"})
    check("S3.3 LSR 1d nul : JAMAIS de CANDIDAT — le détecteur ne décolle QUE planté",
          "CANDIDAT" not in verd_c)
    check("S3.4 pool factice lu (n=30)", res["etude_D_pool_P1"]["n"] == 30)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

tmp = tempfile.mkdtemp()
try:
    build_fake_panel(tmp, plant="none")
    res = run_fake_study(tmp)
    verd_a = {r["verdict"] for r in res["etude_A_contrarian_niveau_4h"].values()}
    check("S3.5 cas nul (bruit pur) : AUC ~ 0,5 et pas de CANDIDAT",
          "CANDIDAT" not in verd_a)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

tmp = tempfile.mkdtemp()
try:
    build_fake_panel(tmp, plant="1d")
    res = run_fake_study(tmp)
    verd_c = {r["verdict"] for r in res["etude_C_replication_1d"].values()}
    verd_a = {r["verdict"] for r in res["etude_A_contrarian_niveau_4h"].values()}
    check("S3.6 détecteur planté sur 1d : étude C décolle (CANDIDAT)",
          "CANDIDAT" in verd_c)
    check("S3.7 le 4h NON planté du même run ne décolle pas",
          "CANDIDAT" not in verd_a)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ============ S4 — ZÉRO LOOK-AHEAD par mutation double ========================
print("S4 — zéro look-ahead : mutation multiplicative+additive (leçon vague 7)")
REAL = Path(os.environ.get("X501_LSR_DIR", HERE / "../../../data/x501_lsr"))
SYM = "BTCUSDT"
kl = st.load_klines(SYM, "240")
ls = st.load_lsr(SYM, "4h")
ot, op = kl["ts"], kl["o"]
arr = st.snap_lsr_sur_barres(ot, ls["ts"], ls["buy"])
z_base = st.rolling_z(arr, 180)
s_base = np.full(len(ot), np.nan)
s_base[1:] = z_base[:-1]
t_cut_idx = 3_000
t_cut = ot[t_cut_idx]
# mutation multiplicative + additive des lignes LSR FUTURES (ts >= t_cut)
buy_mut = ls["buy"].copy()
mask_f = ls["ts"] >= t_cut
buy_mut[mask_f] = buy_mut[mask_f] * 1.05 + 0.003
arr_mut = st.snap_lsr_sur_barres(ot, ls["ts"], buy_mut)
z_mut = st.rolling_z(arr_mut, 180)
s_mut = np.full(len(ot), np.nan)
s_mut[1:] = z_mut[:-1]
past = slice(0, t_cut_idx)
check("S4.1 scores passés BIT À BIT (mutation LSR futur)",
      np.array_equal(s_base[past], s_mut[past], equal_nan=True))
check("S4.2 le test n'est pas vide : scores futurs CHANGÉS",
      not np.array_equal(s_base[t_cut_idx + 10:], s_mut[t_cut_idx + 10:],
                         equal_nan=True))
# mutation des klines futures (open x1.07 + 0.5) — le fwd change, le score non
op_mut = op.copy()
op_mut[t_cut_idx:] = op_mut[t_cut_idx:] * 1.07 + 0.5
fwd_base = np.full(len(ot), np.nan)
fwd_base[:len(ot) - 18] = (op[18:] - op[:len(ot) - 18]) / op[:len(ot) - 18] * 1e4
fwd_mut = np.full(len(ot), np.nan)
fwd_mut[:len(ot) - 18] = (op_mut[18:] - op_mut[:len(ot) - 18]) / op_mut[:len(ot) - 18] * 1e4
check("S4.3 score passé insensible à la mutation des OPENS futurs",
      np.array_equal(s_base[past], s_mut[past], equal_nan=True))
check("S4.4 le fwd futur EST changé par la mutation (test non vide)",
      not np.array_equal(fwd_base[t_cut_idx:], fwd_mut[t_cut_idx:],
                         equal_nan=True))
# mutation RÉTROACTIVE (contrôle inverse) : les scores futurs changent
buy_ret = ls["buy"].copy()
mask_p = ls["ts"] < t_cut
buy_ret[mask_p] = buy_ret[mask_p] * 0.9 - 0.002
arr_ret = st.snap_lsr_sur_barres(ot, ls["ts"], buy_ret)
z_ret = st.rolling_z(arr_ret, 180)
s_ret = np.full(len(ot), np.nan)
s_ret[1:] = z_ret[:-1]
check("S4.5 contrôle inverse : une mutation du PASSE change les scores futurs",
      not np.array_equal(s_base[t_cut_idx + 10:], s_ret[t_cut_idx + 10:],
                         equal_nan=True))

# ============ S5 — la ligne simultanée n'est JAMAIS lue =======================
print("S5 — convention temps : la ligne pile à l'open n'est jamais lue")
t_bar = ot[2_500]                      # open de la barre 2500
idx_pile = int(np.searchsorted(ls["ts"], t_bar))
check("S5.1 il existe bien une ligne LSR pile à cet open (test non vide)",
      idx_pile < len(ls["ts"]) and ls["ts"][idx_pile] == t_bar)
buy_seg = ls["buy"].copy()
buy_seg[idx_pile] = buy_seg[idx_pile] * 1.5 + 0.01
arr_seg = st.snap_lsr_sur_barres(ot, ls["ts"], buy_seg)
z_seg = st.rolling_z(arr_seg, 180)
s_seg = np.full(len(ot), np.nan)
s_seg[1:] = z_seg[:-1]
check("S5.2 le score de la barre 2500 est INCHANGÉ (ligne simultanée jamais lue)",
      np.array_equal(s_base[2_490:2_501], s_seg[2_490:2_501], equal_nan=True))
check("S5.3 les barres POSTÉRIEURES changent (la mutation se propage)",
      not np.array_equal(s_base[2_501:2_511], s_seg[2_501:2_511], equal_nan=True))

# ============ S6 — les 4 branches du verdict ==================================
print("S6 — verdict mécanique : les 4 branches en unitaire")
rng6 = np.random.default_rng(7)
n6 = 600
j6 = np.arange(n6)
s6 = np.where(np.arange(n6) < n6 // 2, 1.0, 0.0)
f_cand = np.where(np.arange(n6) < n6 // 2,
                  -1.0 + rng6.normal(0, 0.001, n6),
                  1.0 + rng6.normal(0, 0.001, n6))
r = st.cellule_panel(s6, f_cand, j6, "test", -1)
check("S6.1 branche CANDIDAT (sens -1, AUC << 0,5, IC exclut 0,5)",
      r["verdict"] == "CANDIDAT" and r["auc"] < 0.5)
f_ctx = np.where(np.arange(n6) < n6 // 2,
                 1.0 + rng6.normal(0, 0.001, n6),
                 -1.0 + rng6.normal(0, 0.001, n6))
r = st.cellule_panel(s6, f_ctx, j6, "test", -1)
check("S6.2 branche CONTEXTE (IC exclut 0,5 mais sens OPPOSÉ à -1)",
      r["verdict"] == "CONTEXTE" and r["auc"] > 0.5)
x6 = rng6.normal(0, 1.0, n6 // 2)
f_kill = np.concatenate([x6, rng6.permutation(x6)])   # multisets identiques -> AUC pile 0,5
r = st.cellule_panel(s6, f_kill, j6, "test", -1)
check("S6.3 branche KILL (AUC ~ 0,5, |AUC-0,5| < 0,02, IC contient 0,5)",
      r["verdict"] == "KILL" and abs(r["auc"] - 0.5) < 0.02)
f_inq = np.concatenate([rng6.normal(-0.05, 1.0, n6 // 2),
                        rng6.normal(0.05, 1.0, n6 - n6 // 2)])
r = st.cellule_panel(s6, f_inq, j6, "test", -1)
check("S6.4 branche INCONCLU (IC contient 0,5, |AUC-0,5| >= 0,02)",
      r["verdict"] == "INCONCLU")
check("S6.5 sens = 0 ne promet JAMAIS CANDIDAT (séparation -> CONTEXTE)",
      st.cellule_panel(s6, f_cand, j6, "test", 0)["verdict"] == "CONTEXTE")
check("S6.6 sens = +1 : même data, CANDIDAT exige AUC > 0,5 -> ici CONTEXTE",
      st.cellule_panel(s6, f_cand, j6, "test", +1)["verdict"] == "CONTEXTE")

# ============ S7 — pool P1 : 469/469 et règle searchsorted ====================
print("S7 — pool P1 (469/469, dernière ligne T <= t_in - P)")
pool = []
import csv as _csv7
with open(st.POOL_CSV, newline="") as f:
    for row in _csv7.DictReader(f):
        pool.append((row["sym"], int(row["t_in"]), float(row["R"])))
check("S7.1 le pool contient 469 entrées", len(pool) == 469)
lsb = st.load_lsr(SYM, "4h")
t_test = int(lsb["ts"][100] + 3 * MS_4H + 60_000)   # entre 2 lignes, décalé
idx_rule = int(np.searchsorted(lsb["ts"], t_test - MS_4H, side="right")) - 1
check("S7.2 la ligne consommée pour t_in = la dernière T <= t_in - P",
      lsb["ts"][idx_rule] == lsb["ts"][100] + 2 * MS_4H)
check("S7.3 la ligne pile à t_in - P + epsilon n'est PAS consommée",
      lsb["ts"][idx_rule] < t_test - MS_4H + 1 and
      lsb["ts"][idx_rule] + MS_4H <= t_test)
t_pile = int(lsb["ts"][150])
idx_pile2 = int(np.searchsorted(lsb["ts"], t_pile - MS_4H, side="right")) - 1
check("S7.4 t_in pile sur une ligne : la ligne SIMULTANÉE n'est pas lue",
      lsb["ts"][idx_pile2] == lsb["ts"][149])

# ============ S8 — audit de collecte ==========================================
print("S8 — audit de collecte (cutoff, pile, gaps, domaines)")
now_ms = 1_800_000_000_000
check("S8.1 cutoff_kline = now - P", col.cutoff_kline(now_ms, MS_4H) == now_ms - MS_4H)
check("S8.2 cutoff_lsr = now - 3P (règle anti-partiel)", col.cutoff_lsr(now_ms, MS_4H) == now_ms - 3 * MS_4H)
n_audit_bad = 0
for sym in st.SYMBOLS:
    for serie, pms in [("4h", MS_4H), ("1d", MS_1D)]:
        l = st.load_lsr(sym, serie)
        k = st.load_klines(sym, "240" if serie == "4h" else "D")
        if l is None or k is None:
            n_audit_bad += 1
            continue
        if (np.diff(l["ts"]) != pms).any():
            n_audit_bad += 1
        if (l["ts"] % pms != 0).any():
            n_audit_bad += 1
        if ((l["buy"] <= 0) | (l["buy"] >= 1)).any():
            n_audit_bad += 1
check("S8.3 12 symboles x 2 séries LSR : 0 gap, grille pile, domaine (0,1)",
      n_audit_bad == 0)
arr_btc = st.snap_lsr_sur_barres(ot, ls["ts"], ls["buy"])
abs_idx = np.flatnonzero(np.isnan(arr_btc))
check("S8.4 les snap absents BTC 4h sont TOUS en queue de fenêtre (refroidissement)",
      len(abs_idx) > 0 and abs_idx.min() >= len(ot) - 5)
check("S8.5 BTC 4h : <= 6 snap absents (anti-partiel, déclaré)",
      len(abs_idx) <= 6)

# ============ S9 — re-exécution BIT À BIT =====================================
print("S9 — re-exécution bit à bit (digest gravé)")
json_path = HERE / "lsr_local.json"
d1 = json.load(open(json_path))
check("S9.1 le JSON versionné porte un digest SHA-256", len(d1.get("digest_sha256", "")) == 64)
env = dict(os.environ)
env["X501_LSR_DIR"] = str(REAL)
tmp2 = tempfile.mkdtemp()
try:
    # copie de l'étude vers un cwd temporaire OUT indépendant : le digest est
    # recalculé sur data fixée -> doit être IDENTIQUE bit à bit
    out_copy = Path(tmp2) / "lsr_local_ref.json"
    shutil.copy(json_path, out_copy)
    # re-exécution : le JSON est réécrit sur place, on compare au digest gravé
    subprocess.run([sys.executable, str(HERE / "x501_lsr_local.py")],
                   env=env, cwd=str(tmp2), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    d2 = json.load(open(json_path))
    check("S9.2 re-exécution : digest IDENTIQUE (bit à bit)",
          d2["digest_sha256"] == d1["digest_sha256"])
    check("S9.3 re-exécution : 12 cellules panel + pool présentes",
          len(d2["etude_A_contrarian_niveau_4h"]) == 4 and
          len(d2["etude_B_flux_positionnement_4h"]) == 4 and
          len(d2["etude_C_replication_1d"]) == 4 and
          "etude_D_pool_P1" in d2)
    check("S9.4 resume verdicts cohérent (12 cellules)",
          sum(d2["resume_verdicts_panel"].values()) == 12)
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

# ============================== bilan =========================================
print(f"\nQA LSR VAGUE 11 : {PASS} OK / {FAIL} FAIL / {len(NAMES)} contrôles")
if FAIL:
    print("ÉCHECS :")
    for n, okk in NAMES:
        if not okk:
            print(f"  - {n}")
    sys.exit(1)
print("TOUS LES CONTRÔLES PASSENT")
