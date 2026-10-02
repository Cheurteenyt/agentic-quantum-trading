#!/usr/bin/env python
# ARCHIVÉ (02/10/2026) — INV-D : FAIL triple réfutation (docs/38, budget consommé)
# INV-D « L'ASYMÉTRIE DE VITESSE » — one-shot pré-enregistré 02/10/2026
# Gouvernance : docs/38-gouvernance-recherche.md, tag freeze-2026-10-02.
# Pré-enregistrement : reports/aster/inv-d-asymetrie-vitesse-2026-10.md
# Seal sha256 du pré-enregistrement (avant toute exécution) :
#   b73bc5d30da139963620645888e632c84a65c152b4decc0cdc847c36f6f11898
# A_t = fraction des 24 closes passés au-dessus du close courant (statistique
# de TEMPS, sans magnitude). Événement = A_t <= q10 calibré TRAIN seulement.
# Hypothèse : extrême bas -> REBOND (espérance nette 24-72h > 0, train ET val).
# PASS/FAIL gravés dans le pré-enregistrement. Budget = 1 expérience, STOP après.
# DB en LECTURE SEULE (uri mode=ro). Aucune écriture hors stdout.
import sqlite3
import datetime as dt
from collections import Counter
import numpy as np

DB = "file:data/warehouse/klines.db?mode=ro"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
WIN = 24                 # fenêtre glissante 24 closes (t-24..t-1)
HORIZONS = [24, 48, 72]  # heures, sorties au close t+h (même entrée open t+1)
COST_RT = 0.0018         # 18 bps round-trip
GRACE_MS = 3 * 3600_000  # tolérance barre manquante (+3h max)

con = sqlite3.connect(DB, uri=True)
cur = con.cursor()
series = {}
for s in SYMBOLS:
    rows_ = cur.execute(
        "SELECT open_time, open, close FROM klines "
        "WHERE symbol=? AND interval='1h' ORDER BY open_time", (s,)
    ).fetchall()
    seen, ts, op, cl = set(), [], [], []
    for t, o, c in rows_:
        if t in seen:
            continue
        seen.add(t)
        ts.append(t); op.append(o); cl.append(c)
    series[s] = (np.array(ts, dtype=np.int64), np.array(op), np.array(cl))
con.close()

tmin = min(int(v[0][0]) for v in series.values())
tmax = max(int(v[0][-1]) for v in series.values())
ts_split = tmin + int(0.60 * (tmax - tmin))
fmt = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
print(f"panel min={fmt(tmin)} max={fmt(tmax)} | SPLIT 60/40 GLOBAL = {fmt(ts_split)}")

def net_long(r):  return (1.0 + r) * (1.0 - COST_RT) - 1.0
def net_short(r): return (1.0 - r) * (1.0 - COST_RT) - 1.0

# ── A_t + forward calculés UNE fois par point ──
# rows: dict par symbole -> listes (i, ts, A, split, fwd) ; fwd=None si abandonné
rows = []
for s in SYMBOLS:
    ts, op, cl = series[s]
    n = len(ts)
    for i in range(WIN, n):
        A = float(np.mean(cl[i - WIN:i] > cl[i]))
        split = "train" if ts[i] < ts_split else "val"
        # entrée : première barre >= ts[i]+1h, tolérance +3h
        tgt_in = int(ts[i]) + 3600_000
        j = int(np.searchsorted(ts, tgt_in, side="left"))
        fwd = None
        if j < n and ts[j] <= tgt_in + GRACE_MS:
            entry = float(op[j]); entry_ts = int(ts[j])
            outs = {}
            ok = True
            for h in HORIZONS:
                tgt = int(ts[i]) + h * 3600_000
                k = int(np.searchsorted(ts, tgt, side="left"))
                if k >= n or ts[k] > tgt + GRACE_MS:
                    ok = False; break
                outs[h] = (float(cl[k]) / entry - 1.0, int(ts[k]))
            if ok:
                fwd = {"entry_ts": entry_ts, **outs}
        rows.append((s, i, int(ts[i]), A, split, fwd))

dropped = sum(1 for r in rows if r[5] is None)
A_train = np.array([r[3] for r in rows if r[4] == "train"])
q10 = float(np.quantile(A_train, 0.10))
q90 = float(np.quantile(A_train, 0.90))
edges = np.quantile(A_train, [k / 10 for k in range(1, 10)])
print(f"points valides={len(rows)} abandonnés(sans forward complet)={dropped}")
print(f"A_train n={len(A_train)} | q10={q10:.4f} q90={q90:.4f} | A_train moy={A_train.mean():.4f}")
print(f"bornes déciles TRAIN: {[round(float(e), 4) for e in edges]}")

ev_events = [r for r in rows if r[5] is not None and r[3] <= q10]
mi_events = [r for r in rows if r[5] is not None and r[3] >= q90]
print(f"\névénements A<=q10 : {len(ev_events)}")
print(f"miroir  A>=q90   : {len(mi_events)} (contexte descriptif)")

def block_stats(evs, label):
    print(f"\n── {label} ──")
    for sp in ["train", "val"]:
        sub = [e for e in evs if e[4] == sp]
        if not sub:
            print(f"  {sp}: 0 événement"); continue
        line = f"  {sp}: n={len(sub)}"
        means, grosses = [], []
        for h in HORIZONS:
            L = np.array([net_long(e[5][h][0]) for e in sub])
            G = np.array([e[5][h][0] for e in sub])
            S = np.array([net_short(e[5][h][0]) for e in sub])
            means.append(float(L.mean()))
            grosses.append(float(G.mean()))
            line += f" | h{h} L {L.mean()*1e4:+.1f}bps (WR {100*np.mean(L>0):.1f}%) S {S.mean()*1e4:+.1f}bps"
        line += f" || BLOC 24-72 net {np.mean(means)*1e4:+.1f}bps brut {np.mean(grosses)*1e4:+.1f}bps"
        print(line)

block_stats(ev_events, "ÉVÉNEMENTS capitulation-par-le-temps (A<=q10, LONG vs SHORT=contrôle continuation)")
block_stats(mi_events, "MIROIR contexte descriptif (A>=q90, hors pass/fail)")

# ── gradient déciles (bornes TRAIN, TOUS les points, par split) ──
print("\n── GRADIENT déciles de A (espérance nette 24h, bornes TRAIN) ──")
mono = {}
for sp in ["train", "val"]:
    vals = {d: [] for d in range(10)}
    for (s, i, t, A, split, fwd) in rows:
        if split != sp or fwd is None:
            continue
        d = int(np.searchsorted(edges, A, side="right"))
        vals[d].append(net_long(fwd[24][0]))
    means = [np.mean(vals[d]) if vals[d] else np.nan for d in range(10)]
    counts = [len(vals[d]) for d in range(10)]
    print(f"  {sp}: means(%) = {[round(100*m, 3) if not np.isnan(m) else None for m in means]}")
    print(f"  {sp}: n       = {counts}")
    mm = [m for m in means if not np.isnan(m)]
    inv = sum(1 for a, b in zip(mm, mm[1:]) if b > a)
    mono[sp] = (inv <= 1 and mm[0] >= max(mm))
    print(f"  {sp}: inversions adjacentes={inv}, d1=max={mm[0] >= max(mm)} -> monotone={'OUI' if mono[sp] else 'NON'}")

# ── BLOC STATS mensuel : trades premier-arrivé (1 position/symbole, trade 24h) ──
print("\n── BLOC STATS mensuel (premier-arrivé par symbole, LONG 1x 24h, notionnel fixe) ──")
trades, last_exit = [], {}
for e in sorted(ev_events, key=lambda r: r[5]["entry_ts"]):
    s = e[0]
    if s in last_exit and e[5]["entry_ts"] <= last_exit[s]:
        continue
    r, exit_ts = e[5][24]
    trades.append({"s": s, "entry_ts": e[5]["entry_ts"], "net": net_long(r)})
    last_exit[s] = exit_ts
print(f"trades premier-arrivé: {len(trades)} (vs {len(ev_events)} événements bruts)")
months = {}
for t in trades:
    m = dt.datetime.fromtimestamp(t["entry_ts"] / 1000, dt.timezone.utc).strftime("%Y-%m")
    months.setdefault(m, []).append(t["net"])
cum = peak = dd = 0.0
rows_m = []
for m in sorted(months):
    ns = np.array(months[m])
    s_ = float(ns.sum())
    cum += s_
    peak = max(peak, cum)
    dd = max(dd, peak - cum)
    rows_m.append((m, len(ns), 100 * float(np.mean(ns > 0)), 100 * s_))
    print(f"  {m}: trades={len(ns):4d} WR_net={100*np.mean(ns>0):5.1f}% net={100*s_:+8.2f}%")
tot = sum(t["net"] for t in trades)
wr = 100 * np.mean([t["net"] > 0 for t in trades])
n_neg = sum(1 for r in rows_m if r[3] < 0)
best = max(rows_m, key=lambda r: r[3]); worst = min(rows_m, key=lambda r: r[3])
span_y = (max(t["entry_ts"] for t in trades) - min(t["entry_ts"] for t in trades)) / 86400_000 / 365.25
print(f"  TOTAL: trades={len(trades)} WR_net={wr:.1f}% liqs=0 cumul={100*tot:+.2f}% "
      f"ROI/an≈{100*tot/max(span_y, 1e-9):+.1f}% DD={100*dd:.2f}% "
      f"record={best[0]} {best[3]:+.1f}% pire={worst[0]} {worst[3]:+.1f}% mois_nég={n_neg}/{len(rows_m)}")
print("  garde-fou composé-des-mois vs final: cumul des mois = cumul total par construction (notionnel fixe)")

# ── taux d'événements par symbole/split (honnêteté panel déséquilibré) ──
print("\n── taux d'événements par symbole/split ──")
cnt = Counter((e[0], e[4]) for e in ev_events)
tot_sym = Counter((r[0], r[4]) for r in rows)
for s in SYMBOLS:
    tr, va = tot_sym[(s, "train")], tot_sym[(s, "val")]
    print(f"  {s:9s} train {cnt[(s,'train')]:5d}/{tr:6d} ({100*cnt[(s,'train')]/max(tr,1):4.1f}%) "
          f"val {cnt[(s,'val')]:5d}/{va:6d} ({100*cnt[(s,'val')]/max(va,1):4.1f}%)")

# ── VERDICT mécanique (critères pré-enregistrés) ──
def blk(sp):
    sub = [e for e in ev_events if e[4] == sp]
    return float(np.mean([np.mean([net_long(e[5][h][0]) for e in sub]) for h in HORIZONS]))
def ctl(sp):
    sub = [e for e in ev_events if e[4] == sp]
    return [(float(np.mean([net_long(e[5][h][0]) for e in sub])),
             float(np.mean([net_short(e[5][h][0]) for e in sub]))) for h in HORIZONS]
n_train = sum(1 for e in ev_events if e[4] == "train")
print("\n── VERDICT (critères pré-enregistrés) ──")
if n_train < 100:
    print(f"SOUS-PUISANT (n train={n_train} < 100) — non tranchable, pas un FAIL d'hypothèse")
else:
    bt, bv = blk("train"), blk("val")
    ok1 = bt > 0 and bv > 0
    ok2 = all(L > S for L, S in ctl("train")) and all(L > S for L, S in ctl("val"))
    ok3 = mono["train"] and mono["val"]
    ct = ctl("train"); cv = ctl("val")
    print(f"n train={n_train} | bloc 24-72 net: train {1e4*bt:+.1f}bps val {1e4*bv:+.1f}bps -> >0 train&val: {ok1}")
    print(f"contrôle inverse (long>short, bps L/S): train "
          f"{[(round(1e4*L,1), round(1e4*S,1)) for L,S in ct]} val {[(round(1e4*L,1), round(1e4*S,1)) for L,S in cv]} -> battu: {ok2}")
    print(f"gradient monotone d1->d10: train {mono['train']} val {mono['val']} -> {ok3}")
    print("VERDICT: " + ("PASS — hypothèse validée (CANDIDATE, wallet séquentiel requis avant stack)"
                        if (ok1 and ok2 and ok3) else "FAIL — hypothèse réfutée (budget consommé, STOP)"))
