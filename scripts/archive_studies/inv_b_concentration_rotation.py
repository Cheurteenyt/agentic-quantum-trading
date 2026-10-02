# INV-B — « LA CONCENTRATION-ROTATION » (one-shot pré-enregistré, 02/10/2026)
# ARCHIVÉ (02/10/2026) — INV-B : FAIL hypothèse réfutée (docs/38, budget consommé)
# Gouvernance : docs/38 tag freeze-2026-10-02 — UNE expérience, zéro grille,
# critères PASS/FAIL écrits AVANT dans reports/aster/inv-b-concentration-rotation-2026-10.md.
# DB en LECTURE SEULE. Ne touche ni the_machine, ni paper_forward, ni collecteurs.
#Interdit de re-run avec une autre fenêtre / quantile : budget = 1 expérience.

import sqlite3
import numpy as np
from collections import defaultdict

DB = "file:/run/media/cheurteen/Jeux SSD/trading-agent/data/warehouse/klines.db?mode=ro"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
H = 24  # fenêtre de volume 24h (barres 1h)
AFTER = (24, 72)  # fenêtre de mesure [t+24h, t+72h]
COST = 0.0036  # 36 bps RT par paire (2 jambes taker 18)

con = sqlite3.connect(DB, uri=True)
cur = con.cursor()

# --- chargement 1h (open_time en ms, unité vérifiée) ---
data = {}
for s in SYMS:
    rows = cur.execute(
        "SELECT open_time, close, quote_volume FROM klines "
        "WHERE symbol=? AND interval='1h' ORDER BY open_time", (s,)).fetchall()
    data[s] = {int(t): (float(c), float(q if q is not None else np.nan)) for t, c, q in rows}
con.close()

grid_start = max(min(d) for d in data.values())
grid_end = min(max(d) for d in data.values())
grid = [t for t in sorted(set().union(*[set(d) for d in data.values()]))
        if grid_start <= t <= grid_end]
print(f"grille commune 1h : {len(grid)} heures "
      f"({__import__('datetime').datetime.utcfromtimestamp(grid_start/1000):%Y-%m-%d %H:%M} -> "
      f"{__import__('datetime').datetime.utcfromtimestamp(grid_end/1000):%Y-%m-%d %H:%M} UTC)")

# --- H_t sur chaque close où les 6 majeures ont 24 barres complètes ---
ts_list, H_list, vol_list = [], [], []
n_missing_vol = 0
for i, t in enumerate(grid):
    if i < H - 1:
        continue
    window = grid[i - H + 1: i + 1]
    vols = []
    ok = True
    for s in SYMS:
        v = [data[s].get(w, (np.nan, np.nan))[1] for w in window]
        if any(np.isnan(x) for x in v):
            ok = False
            break
        vols.append(float(np.sum(v)))
    if not ok:
        n_missing_vol += 1
        continue
    tot = sum(vols)
    if tot <= 0:
        n_missing_vol += 1
        continue
    h_t = sum(v * v for v in vols) / (tot * tot)
    ts_list.append(t)
    H_list.append(h_t)
    vol_list.append(vols)

ts_arr = np.array(ts_list)
H_arr = np.array(H_list)
vol_arr = np.array(vol_list)
print(f"heures mesurables H_t : {len(ts_arr)} (exclues pour trous 24h : {n_missing_vol})")

# --- split 60/40 chrono GLOBAL ---
N = len(ts_arr)
split = int(np.floor(0.6 * N))
H_train, H_val = H_arr[:split], H_arr[split:]
q95 = float(np.quantile(H_train, 0.95))
print(f"split 60/40 : train {split} h | val {N - split} h")
print(f"quantile 95 de H_t (TRAIN SEULEMENT) : {q95:.6f}")
print(f"H_train min/med/max : {H_train.min():.4f}/{np.median(H_train):.4f}/{H_train.max():.4f} "
      f"| H_val max : {H_val.max():.4f}")

# --- événements + mesure relative [t+24h, t+72h] ---
def idx_of(ts):
    return int(np.searchsorted(ts_arr, ts))

events = []  # (t, split, H_t, concentrée, ret_c, med5, REL_gross)
n_excl_meas = 0
for i in range(N):
    if H_arr[i] < q95:
        continue
    t = ts_arr[i]
    sp = "TRAIN" if i < split else "VAL"
    t0, t1 = t + AFTER[0] * 3600_000, t + AFTER[1] * 3600_000
    closes0, closes1 = [], []
    ok = True
    for s in SYMS:
        c0 = data[s].get(t0)
        c1 = data[s].get(t1)
        if c0 is None or c1 is None:
            ok = False
            break
        closes0.append(c0[0])
        closes1.append(c1[0])
    if not ok:
        n_excl_meas += 1
        continue
    rets = np.array(closes1) / np.array(closes0) - 1.0
    ci = int(np.argmax(vol_arr[i]))  # concentrée = max volume 24h
    others = [r for j, r in enumerate(rets) if j != ci]
    ret_c = rets[ci]
    med5 = float(np.median(others))
    events.append((t, sp, float(H_arr[i]), SYMS[ci], ret_c, med5, med5 - ret_c))

print(f"événements (H_t >= q95) : {len(events)} "
      f"| exclus faute de barres t+24/72 : {n_excl_meas}")
ev_train = [e for e in events if e[1] == "TRAIN"]
ev_val = [e for e in events if e[1] == "VAL"]
print(f"  TRAIN : {len(ev_train)} | VAL : {len(ev_val)}")

# --- stats ---
def block(evs, name):
    if not evs:
        print(f"[{name}] aucun événement")
        return {}
    gross = np.array([e[6] for e in evs])
    net = gross - COST
    inv = -gross  # contrôle inverse BRUT : ret_c - med5 = -(med5 - ret_c)
    r = {
        "n": len(evs),
        "mean_gross": float(gross.mean()), "med_gross": float(np.median(gross)),
        "mean_net": float(net.mean()), "med_net": float(np.median(net)),
        "wr_net": float((net > 0).mean()),
        "inv_mean_gross": float(inv.mean()), "inv_med_gross": float(np.median(inv)),
    }
    print(f"[{name}] n={r['n']} | REL_gross mean {r['mean_gross']*100:+.3f}% med {r['med_gross']*100:+.3f}% "
          f"| REL_net mean {r['mean_net']*100:+.3f}% med {r['med_net']*100:+.3f}% | WR_net {r['wr_net']*100:.1f}% "
          f"| inverse brut mean {r['inv_mean_gross']*100:+.3f}% med {r['inv_med_gross']*100:+.3f}%")
    return r

tr = block(ev_train, "TRAIN")
va = block(ev_val, "VAL")

# --- gradient terciles de H_t (parmi les événements) ---
def terciles(evs, name, edges=None):
    if not evs:
        return None
    hv = np.array([e[2] for e in evs])
    nv = np.array([e[6] - COST for e in evs])
    if edges is None:
        edges = np.quantile(hv, [1 / 3, 2 / 3])
    out = []
    for k, m in enumerate([hv <= edges[0],
                           (hv > edges[0]) & (hv <= edges[1]),
                           hv > edges[1]]):
        out.append(float(np.median(nv[m])) if m.any() else float("nan"))
    print(f"[{name}] terciles H (bords {edges[0]:.4f}/{edges[1]:.4f}) : "
          f"T1 {out[0]*100:+.3f}% | T2 {out[1]*100:+.3f}% | T3 {out[2]*100:+.3f}% "
          f"(n {[int(m.sum()) for m in [hv <= edges[0], (hv > edges[0]) & (hv <= edges[1]), hv > edges[1]]]})")
    return out, edges

res_t = terciles(ev_train, "TRAIN")
if res_t and va and va["n"] > 0:
    terciles(ev_val, "VAL", edges=res_t[1])
mono_train = res_t and res_t[0][0] <= res_t[0][1] <= res_t[0][2]

# --- concentrateur stats : qui est la concentrée ? ---
cc = defaultdict(int)
for e in events:
    cc[e[3]] += 1
print("concentrée par événement :", dict(sorted(cc.items(), key=lambda x: -x[1])))

# --- BLOC STATS mensuel ---
mon = defaultdict(lambda: {"n": 0, "sum_net": 0.0, "win": 0})
for t, sp, h, c, rc, m5, g in events:
    import datetime as dt
    key = (dt.datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m"), sp)
    mon[key]["n"] += 1
    mon[key]["sum_net"] += g - COST
    mon[key]["win"] += 1 if (g - COST) > 0 else 0
print("\nBLOC STATS MENSUEL (mois | split | n | WR_net % | somme REL_net %) :")
for k in sorted(mon):
    m = mon[k]
    print(f"  {k[0]} | {k[1]} | n={m['n']} | WR {100*m['win']/m['n']:.0f}% | somme {m['sum_net']*100:+.2f}%")

# --- courbe cumulée (somme non composée, sans levier) + DD ---
cum = np.cumsum([e[6] - COST for e in sorted(events, key=lambda x: x[0])])
peak = np.maximum.accumulate(np.concatenate([[0], cum]))[1:]
dd = float(np.max(peak - cum))
neg_months = sum(1 for k in mon if mon[k]["sum_net"] < 0)
sums = [mon[k]["sum_net"] for k in sorted(mon)]
print(f"\ncumul total REL_net (non composé, sans levier) : {cum[-1]*100:+.2f}% | DD max courbe cumulée : {dd*100:.2f} pts")
print(f"mois négatifs (somme net < 0) : {neg_months}/{len(mon)} | pire mois {min(sums)*100:+.2f}% | record mois {max(sums)*100:+.2f}%")
print(f"liquidations : 0 (aucun levier, spread relatif)")

# --- VERDICT mécanique ---
underpowered = tr["n"] < 80
has_val = va.get("n", 0) > 0
c1 = (tr["mean_net"] > 0) and (has_val and va["mean_net"] > 0)
c2 = (tr["inv_mean_gross"] < 0) and (has_val and va["inv_mean_gross"] < 0)
c3 = bool(mono_train)
print(f"\nVÉRIF CRITÈRES : n_train>=80 : {not underpowered} (n={tr['n']}) | "
      f"espérance nette >0 train&val : {c1} | inverse brut battu train&val : {c2} | "
      f"gradient monotone train : {c3}")
if underpowered:
    print("VERDICT : SOUS-PUISSENT (n_train < 80) — déclaré tel quel")
elif c1 and c2 and c3:
    print("VERDICT : PASS")
else:
    print("VERDICT : FAIL — hypothèse réfutée (budget consommé, STOP, pas de deuxième quantile ni fenêtre)")
