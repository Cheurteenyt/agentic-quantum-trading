#!/usr/bin/env python3
# ARCHIVÉ (02/10/2026) — INV-H : FAIL artefact de base-rate attrapé par le critère pré-déclaré (docs/38)
# INV-H — « LA SUPERPOSITION DE RÉGIMES » (one-shot, pré-enregistré 02/10/2026)
# Gouvernance : docs/38-gouvernance-recherche.md, tag freeze-2026-10-02.
# Rapport : reports/aster/inv-h-superposition-regimes-2026-10.md
# Seal pré-enregistrement : d9d1fb829ca98223e201f796a603930b0cba7d625c6e8919f991970fb9dd523f
# Protocole : split 60/40 chrono global fixé avant le fit ; HMM gaussien 3 états diagonal
# PAR SÉRIE (BTC, ETH), features (ret 1h, rv24), fit EM (Baum-Welch échelle Rabiner,
# numpy pur — hmmlearn absent) sur TRAIN ONLY, filtre causal continu sur la série
# entière, critère = précision de prédiction de l'état crisp à t+168h :
# HMM (argmax de pi_t @ A^168) vs naïf (crisp à t). AUCUN re-fit sur VAL,
# AUCUN trade, 0 liq par construction. Budget = 1 expérience.

import sqlite3
import numpy as np
from datetime import datetime, timezone

DB = "file:/run/media/cheurteen/Jeux SSD/trading-agent/data/warehouse/klines.db?mode=ro"
SYMS = ("BTCUSDT", "ETHUSDT")
HORIZON = 168          # 7 jours en heures
CRISP_TH = 0.8         # seuil crisp pré-déclaré
K = 3                  # un seul état du protocole : 3 états
MAX_ITER, TOL, V_FLOOR = 300, 1e-6, 1e-8
CANON = ["CRISE", "TENDANCE", "CHOP"]  # index canoniques 0/1/2


def log_emission(X, means, vars_):
    T = X.shape[0]
    out = np.empty((T, K))
    for k in range(K):
        z2 = ((X - means[k]) ** 2) / vars_[k]
        out[:, k] = -0.5 * np.sum(z2 + np.log(2 * np.pi * vars_[k]), axis=1)
    return out


def stationary(A):
    w, v = np.linalg.eig(A.T)
    j = int(np.argmin(np.abs(w - 1.0)))
    s = np.abs(np.real(v[:, j]))
    return s / s.sum()


def hmm_fit(X):
    """Baum-Welch déterministe : init terciles de rv (X[:,1]), EM à échelle."""
    T = X.shape[0]
    q1, q2 = np.quantile(X[:, 1], [1 / 3, 2 / 3])
    lab = np.digitize(X[:, 1], [q1, q2])
    means = np.zeros((K, X.shape[1]))
    vars_ = np.zeros((K, X.shape[1]))
    for k in range(K):
        m = lab == k
        assert m.sum() > 10, "état initial vide"
        means[k] = X[m].mean(axis=0)
        vars_[k] = X[m].var(axis=0) + V_FLOOR
    A = np.full((K, K), 1e-6)
    np.add.at(A, (lab[:-1], lab[1:]), 1.0)
    A /= A.sum(axis=1, keepdims=True)
    pi0 = stationary(A)
    ll_prev = -np.inf
    ll = -np.inf
    for it in range(MAX_ITER):
        B = np.exp(log_emission(X, means, vars_))
        # forward à échelle
        a = np.empty((T, K))
        c = np.empty(T)
        a0 = pi0 * B[0]
        c[0] = max(a0.sum(), 1e-300)
        a[0] = a0 / c[0]
        for t in range(1, T):
            at = (a[t - 1] @ A) * B[t]
            ct = at.sum()
            if ct <= 0:
                raise RuntimeError("underflow forward")
            a[t] = at / ct
            c[t] = ct
        ll = float(np.log(c).sum())
        # backward à échelle
        b = np.empty((T, K))
        b[-1] = 1.0
        for t in range(T - 2, -1, -1):
            bt = A @ (B[t + 1] * b[t + 1])
            b[t] = bt / max(bt.sum(), 1e-300)
        gamma = a * b
        gamma /= gamma.sum(axis=1, keepdims=True)
        xi = a[:-1][:, :, None] * A[None, :, :] * (B[1:] * b[1:])[:, None, :]
        xi /= xi.sum(axis=(1, 2), keepdims=True)
        # M-step
        pi0 = gamma[0] / gamma[0].sum()
        gsum = gamma[:-1].sum(axis=0)
        A = xi.sum(axis=0) / np.maximum(gsum, 1e-300)[:, None]
        A = np.maximum(A, 1e-15)
        A /= A.sum(axis=1, keepdims=True)
        g = gamma.sum(axis=0)
        means = (gamma[:, :, None] * X[:, None, :]).sum(axis=0) / g[:, None]
        d2 = (X[:, None, :] - means[None, :, :]) ** 2
        vars_ = (gamma[:, :, None] * d2).sum(axis=0) / g[:, None]
        vars_ = np.maximum(vars_, V_FLOOR)
        if abs(ll - ll_prev) < TOL:
            break
        ll_prev = ll
    return dict(A=A, pi0=pi0, means=means, vars_=vars_, iters=it + 1, ll=ll)


# ── 1. Données (LECTURE SEULE, leçon ts_ms) ──────────────────────────────────
con = sqlite3.connect(DB, uri=True)
raw = {}
for sym in SYMS:
    rows = con.execute(
        "SELECT open_time, close FROM klines WHERE symbol=? AND interval='1h' ORDER BY open_time",
        (sym,)).fetchall()
    ts = np.array([r[0] for r in rows], dtype=np.int64)
    cl = np.array([r[1] for r in rows], dtype=np.float64)
    assert ts.min() > 10 ** 12, "open_time n'est PAS en ms (leçon ts_ms)"
    assert len(np.unique(ts)) == len(ts), "doublon (symbol, open_time)"
    grid = np.arange(ts[0], ts[-1] + 3_600_000, 3_600_000, dtype=np.int64)
    assert np.array_equal(ts, grid), f"GAP de grille 1h détecté sur {sym} — STOP"
    raw[sym] = (ts, cl)
con.close()
print("== Données (klines.db mode=ro, assertions ms/doublons/grille contiguë OK) ==")
for sym in SYMS:
    ts, _ = raw[sym]
    print(f"  {sym}: {len(ts)} barres 1h, "
          f"{datetime.fromtimestamp(ts[0]/1000, tz=timezone.utc):%Y-%m-%d %H:%M} -> "
          f"{datetime.fromtimestamp(ts[-1]/1000, tz=timezone.utc):%Y-%m-%d %H:%M} UTC")

# ── 2. Features (ret 1h, rv24) par série ; mesurables dès l'index 24 ────────
# ret[i] = close[i]/close[i-1]-1 ; rv24[i] = sqrt(sum des ret² sur les 24 h finissant à i).
feat = {}
for sym in SYMS:
    ts, cl = raw[sym]
    n = len(ts)
    ret = np.full(n, np.nan)
    ret[1:] = cl[1:] / cl[:-1] - 1.0
    r2 = ret[1:] ** 2                       # r2[k] = ret[k+1]^2 (retour finissant à l'heure k+1)
    cs = np.cumsum(r2)
    lo = np.concatenate(([0.0], cs))        # lo[m] = 0 si m==0 sinon cs[m-1]
    rv = np.full(n, np.nan)
    idx = np.arange(24, n)
    rv[idx] = np.sqrt(cs[idx - 1] - lo[idx - 24])   # somme r2[i-24..i-1]
    X = np.column_stack([ret, rv])[idx]
    assert np.isfinite(X).all(), "NaN dans les features"
    feat[sym] = dict(ts=ts[idx], X=X)
    print(f"  {sym}: {X.shape[0]} heures mesurables (index 24..{n-1})")

# ── 3. Split 60/40 chrono GLOBAL (percentile 60 des ts uniques poolés, non arrondi) ──
union_ts = np.unique(np.concatenate([feat[s]["ts"] for s in SYMS]))
T_split = np.percentile(union_ts.astype(np.float64), 60)
print(f"\nT_split (percentile 60, non arrondi) = {T_split:.1f} ms = "
      f"{datetime.fromtimestamp(T_split/1000, tz=timezone.utc):%Y-%m-%d %H:%M:%S.%f} UTC")
for sym in SYMS:
    ts = feat[sym]["ts"]
    print(f"  {sym}: TRAIN {int((ts < T_split).sum())} h / VAL {int((ts >= T_split).sum())} h")

# ── 4. Z-score TRAIN ONLY + fit HMM TRAIN ONLY par série ────────────────────
models, Z = {}, {}
print("\n== Fits Baum-Welch (TRAIN only, params gelés ensuite) ==")
for sym in SYMS:
    ts, X = feat[sym]["ts"], feat[sym]["X"]
    tr = ts < T_split
    mu, sd = X[tr].mean(axis=0), X[tr].std(axis=0)
    assert (sd > 0).all()
    Z[sym] = (X - mu) / sd
    m = hmm_fit(Z[sym][tr])
    models[sym] = m
    st = stationary(m["A"])
    print(f"  {sym}: EM {m['iters']} iters, loglik {m['ll']:.2f} | A diag "
          f"{np.round(np.diag(m['A']), 4)} | stationnaire TRAIN {np.round(st, 4)}")

# ── 5. Filtre causal continu (params TRAIN gelés) + crisp + étiquetage canonique ──
post, crisp, canon_map = {}, {}, {}
print("\n== Filtre causal continu + crisp (posterior max >= 0.8) ==")
for sym in SYMS:
    m = models[sym]
    B = np.exp(log_emission(Z[sym], m["means"], m["vars_"]))
    Tn = B.shape[0]
    a = np.empty((Tn, K))
    a0 = m["pi0"] * B[0]
    a[0] = a0 / a0.sum()
    for t in range(1, Tn):
        at = (a[t - 1] @ m["A"]) * B[t]
        a[t] = at / at.sum()
    p = a / a.sum(axis=1, keepdims=True)
    assert np.isfinite(p).all(), "posterior non fini (underflow filtre) — STOP"
    post[sym] = p
    mx = p.max(axis=1)
    crisp_raw = np.where(mx >= CRISP_TH, p.argmax(axis=1), -1)
    crisp[sym] = crisp_raw
    print(f"  {sym}: couverture crisp = {(crisp_raw >= 0).mean():.1%} "
          f"(heures ambiguës exclues : {(crisp_raw < 0).sum()})")

# Étiquetage : ordre par moyenne TRAIN de rv24 ; CRISE = rv max ; des deux
# restants : TENDANCE = ret moyen TRAIN le plus haut, CHOP = l'autre.
# Re-mappage sur l'index canonique commun (0=CRISE, 1=TENDANCE, 2=CHOP).
for sym in SYMS:
    m = models[sym]
    ts = feat[sym]["ts"]
    tr = ts < T_split
    rv_mean = m["means"][:, 1]               # moyenne TRAIN de rv24 PAR ÉTAT (z, même ordre qu'en brut)
    ret_mean = m["means"][:, 0]              # moyenne TRAIN de ret PAR ÉTAT (z)
    assert tr.sum() > 0
    order = np.argsort(rv_mean)
    k_crise = int(order[-1])
    rest = [int(order[0]), int(order[1])]
    k_tendance = rest[int(np.argmax(ret_mean[rest]))]
    k_chop = rest[1 - int(np.argmax(ret_mean[rest]))]
    canon_map[sym] = {k_crise: 0, k_tendance: 1, k_chop: 2}
    print(f"  {sym}: " + ", ".join(
        f"k{k} -> {CANON[canon_map[sym][k]]} (TRAIN z rv {rv_mean[k]:+.3f}, ret {ret_mean[k]:+.3f})"
        for k in range(K)))

# ── 6. Événements de prédiction t -> t+168 (même split, crisp aux deux bouts) ──
A168 = {sym: np.linalg.matrix_power(models[sym]["A"], HORIZON) for sym in SYMS}
events = []
for sym in SYMS:
    ts, c, p = feat[sym]["ts"], crisp[sym], post[sym]
    n = len(ts)
    sp = (ts >= T_split).astype(np.int8)
    c_canon = np.full(n, -1)
    for k, ck in canon_map[sym].items():
        c_canon[c == k] = ck
    for i in range(n - HORIZON):
        j = i + HORIZON
        if sp[i] != sp[j] or c[i] < 0 or c[j] < 0:
            continue
        pred_raw = int(np.argmax(p[i] @ A168[sym]))   # superposition complète propagée
        events.append((sym, i, int(sp[i]), int(c[i]), canon_map[sym][pred_raw], canon_map[sym][int(c[j])]))
ev_sym = np.array([e[0] for e in events])
ev_i = np.array([e[1] for e in events])
ev_split = np.array([e[2] for e in events])
ev_naive = np.array([e[3] for e in events])
ev_hmm = np.array([e[4] for e in events])
ev_truth = np.array([e[5] for e in events])
print(f"\nÉvénements d'évaluation (crisp à t ET t+{HORIZON}h, même split) : {len(events)} "
      f"(TRAIN {int((ev_split == 0).sum())} / VAL {int((ev_split == 1).sum())})")
SPLIT_NAMES = {0: "TRAIN", 1: "VAL"}


def acc(mask, preds):
    return float((preds[mask] == ev_truth[mask]).mean()) if mask.sum() else float("nan")


# ── 7. Critères 1-2 : précision poolée par split ────────────────────────────
print(f"\n== CRITÈRES 1-2 : poolé BTC+ETH (naïf = crisp(t) ; HMM = argmax(pi_t @ A^{HORIZON})) ==")
crit12 = {}
for sp in (0, 1):
    m = ev_split == sp
    a_n, a_h = acc(m, ev_naive), acc(m, ev_hmm)
    crit12[sp] = (a_n, a_h, (a_h - a_n) * 100)
    print(f"  {SPLIT_NAMES[sp]}: n={int(m.sum())} | naïf {a_n*100:.2f} % | HMM {a_h*100:.2f} % "
          f"| écart {(a_h-a_n)*100:+.2f} pts")

# ── 8. Critère 3 : par état canonique (truth = s), garde n>=100 ─────────────
print("\n== CRITÈRE 3 : avantage par état de vérité terrain (garde n>=100) ==")
crit3_ok = True
crit3_detail = {}
for sp in (0, 1):
    print(f"  -- {SPLIT_NAMES[sp]} --")
    for s in range(3):
        m = (ev_split == sp) & (ev_truth == s)
        n_s = int(m.sum())
        if n_s < 100:
            print(f"    {CANON[s]}: n={n_s} < 100 -> garde descriptif, non falsifiant")
            continue
        a_n, a_h = acc(m, ev_naive), acc(m, ev_hmm)
        ok = a_h > a_n
        crit3_ok &= ok
        crit3_detail[(sp, s)] = (n_s, a_n, a_h, ok)
        print(f"    {CANON[s]}: n={n_s} | naïf {a_n*100:.2f} % | HMM {a_h*100:.2f} % "
              f"| avantage {(a_h-a_n)*100:+.2f} pts | {'OK' if ok else 'ECHEC'}")

# ── 9. Descriptif par série + confusion ─────────────────────────────────────
print("\n== Descriptif par série ==")
for sym in SYMS:
    for sp in (0, 1):
        m = (ev_split == sp) & (ev_sym == sym)
        if not m.sum():
            continue
        a_n, a_h = acc(m, ev_naive), acc(m, ev_hmm)
        print(f"  {sym} {SPLIT_NAMES[sp]}: n={int(m.sum())} | naïf {a_n*100:.2f} % "
              f"| HMM {a_h*100:.2f} % | écart {(a_h-a_n)*100:+.2f} pts")
print("\n== Matrices de confusion (lignes = truth canonique, colonnes = prédiction) ==")
for sp in (0, 1):
    m = ev_split == sp
    for tag, preds in (("NAÏF", ev_naive), ("HMM", ev_hmm)):
        C = np.zeros((K, K), dtype=int)
        for x, y in zip(ev_truth[m], preds[m]):
            C[x, y] += 1
        print(f"  {SPLIT_NAMES[sp]} {tag}: " + " | ".join(
            f"{CANON[s]}: " + " ".join(f"{C[s, j]:6d}" for j in range(K)) for s in range(K)))

# Distribution des états de vérité (descriptif régime)
for sp in (0, 1):
    m = ev_split == sp
    fr = np.array([(ev_truth[m] == s).mean() for s in range(3)])
    print(f"  {SPLIT_NAMES[sp]} fréquence truth: " + " | ".join(
        f"{CANON[s]} {fr[s]:.1%}" for s in range(3)))

# ── 10. BLOC STATS mensuel (mois du temps de décision t) ────────────────────
print(f"\n== BLOC STATS mensuel (poolé BTC+ETH ; mois de t ; couverture = evts / heures éligibles) ==")
# heures éligibles (avant filtre crisp) par (mois, split) pour la couverture
elig = {}
for sym in SYMS:
    ts = feat[sym]["ts"]
    n = len(ts)
    sp = (ts >= T_split).astype(np.int8)
    spf = sp.copy()
    spf[-HORIZON:] = -1
    ok = sp == spf
    mo = ts.astype("datetime64[ms]").astype("datetime64[M]").astype(str)
    for s_, m_ in zip(mo[ok], sp[ok]):
        elig[(s_, int(m_))] = elig.get((s_, int(m_)), 0) + 1
months_arr = {sym: feat[sym]["ts"].astype("datetime64[ms]").astype("datetime64[M]").astype(str)
              for sym in SYMS}
ev_month = np.array([months_arr[ev_sym[q]][ev_i[q]] for q in range(len(events))])
for sp in (0, 1):
    m_sp = ev_split == sp
    for mo in sorted(set(ev_month[m_sp])):
        m = m_sp & (ev_month == mo)
        n = int(m.sum())
        e = elig.get((mo, sp), 0)
        if n == 0:
            continue
        a_n, a_h = acc(m, ev_naive), acc(m, ev_hmm)
        cov = n / e if e else float("nan")
        print(f"  {mo} | {SPLIT_NAMES[sp]} | n={n:6d} | couv {cov:6.1%} | naïf {a_n*100:6.2f} % "
              f"| HMM {a_h*100:6.2f} % | écart {(a_h-a_n)*100:+7.2f} pts")

# ── 11. VERDICT (critères gelés) ────────────────────────────────────────────
print("\n== VERDICT ==")
c1 = crit12[0][0] < crit12[0][1] and crit12[1][0] < crit12[1][1]
c2 = crit12[0][2] >= 5.0 and crit12[1][2] >= 5.0
print(f"  Critère 1 (HMM > naïf en TRAIN ET VAL) : {'OK' if c1 else 'FAUX'}")
print(f"  Critère 2 (écart >= 5 pts dans les deux splits) : {'OK' if c2 else 'FAUX'} "
      f"(TRAIN {crit12[0][2]:+.2f} pts / VAL {crit12[1][2]:+.2f} pts)")
print(f"  Critère 3 (avantage sur les 3 états, garde n>=100) : {'OK' if crit3_ok else 'FAUX'}")
if c1 and c2 and crit3_ok:
    print("  VERDICT : PASS — la superposition prédit la persistance mieux que le naïf "
          "(CONTEXTE/CANDIDATE gate, jamais signal autonome).")
else:
    print("  VERDICT : FAIL — hypothèse réfutée. Budget = 1 expérience, STOP, aucun re-fit ni variante.")
