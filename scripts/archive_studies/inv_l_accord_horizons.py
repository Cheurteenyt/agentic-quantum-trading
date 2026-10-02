#!/usr/bin/env python
# ARCHIVÉ (02/10/2026) — INV-L : FAIL asymétrique, aucun short net sur état baissier persistant (docs/38)
# INV-L « L'ACCORD DES HORIZONS » — one-shot pré-enregistré 02/10/2026
# Gouvernance : docs/38-gouvernance-recherche.md, tag freeze-2026-10-02.
# Pré-enregistrement : reports/aster/inv-l-accord-horizons-2026-10.md
# Construction : à chaque close 1h d'une majeure, signe de ret24, ret72, ret168
# (ret_h = close(t)/close(t-h) − 1, closes connus au close de décision — le
# signal EST le close t, entrée open t+1h). Événement = ACCORD COMPLET (les 3
# même signe). Hypothèse pré-déclarée : accord haussier -> continuation
# positive 24-72h (LONG), accord baissier -> continuation négative (SHORT) ;
# le contrôle inverse (épuisement/retournement) doit être pire.
# PASS/FAIL gravés dans le pré-enregistrement. Budget = 1 expérience,
# STOP après verdict. DB en LECTURE SEULE (uri mode=ro). 1x, 18 bps RT.
import sqlite3
import datetime as dt
from collections import Counter
import numpy as np

DB = "file:data/warehouse/klines.db?mode=ro"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
HORIZONS = [24, 48, 72]        # heures, sorties au close t+h (entrée open t+1)
RETS = [24, 72, 168]           # horizons de signal en barres 1h
COST_RT = 0.0018               # 18 bps round-trip
GRACE_MS = 3 * 3600_000        # tolérance barre manquante (+3h max)

con = sqlite3.connect(DB, uri=True)
cur = con.cursor()
series, rejected_bars = {}, Counter()
for s in SYMBOLS:
    rows_ = cur.execute(
        "SELECT open_time, open, high, low, close FROM klines "
        "WHERE symbol=? AND interval='1h' ORDER BY open_time", (s,)
    ).fetchall()
    seen, ts, op, hi, lo, cl = set(), [], [], [], [], []
    for t, o, h, l, c in rows_:
        if t in seen:
            continue
        seen.add(t)
        if not (h >= max(o, c) and l <= min(o, c)):  # intégrité mèches
            rejected_bars[s] += 1
            continue
        ts.append(t); op.append(o); hi.append(h); lo.append(l); cl.append(c)
    series[s] = (np.array(ts, dtype=np.int64), np.array(op), np.array(hi),
                 np.array(lo), np.array(cl))
con.close()
print("bougies rejetées (intégrité high>=max(o,c) et low<=min(o,c)) :",
      dict(rejected_bars) or 0)

tmin = min(int(v[0][0]) for v in series.values())
tmax = max(int(v[0][-1]) for v in series.values())
ts_split = tmin + int(0.60 * (tmax - tmin))
fmt = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
print(f"panel min={fmt(tmin)} max={fmt(tmax)} | SPLIT 60/40 GLOBAL = {fmt(ts_split)}")

def net_long(r):  return (1.0 + r) * (1.0 - COST_RT) - 1.0
def net_short(r): return (1.0 - r) * (1.0 - COST_RT) - 1.0

# ── signes + forward calculés UNE fois par point ──
rows, zero_sign = [], 0
for s in SYMBOLS:
    ts, op, hi, lo, cl = series[s]
    n = len(ts)
    for i in range(max(RETS), n):
        r24 = cl[i] / cl[i - 24] - 1.0
        r72 = cl[i] / cl[i - 72] - 1.0
        r168 = cl[i] / cl[i - 168] - 1.0
        signs = [np.sign(r24), np.sign(r72), np.sign(r168)]
        npos = int(sum(1 for g in signs if g > 0))
        nneg = int(sum(1 for g in signs if g < 0))
        if (npos + nneg) < 3:
            zero_sign += 1
            continue
        split = "train" if ts[i] < ts_split else "val"
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
        rows.append((s, i, int(ts[i]), npos, nneg, split, fwd))

dropped = sum(1 for r in rows if r[6] is None)
valid = [r for r in rows if r[6] is not None]
print(f"points valides={len(valid)} (abandonnés sans forward complet={dropped}, "
      f"heures à ret nul exclues={zero_sign})")

full_bull = [r for r in valid if r[3] == 3]   # accord complet haussier
full_bear = [r for r in valid if r[4] == 3]   # accord complet baissier
part_bull = [r for r in valid if r[3] == 2 and r[4] == 1]  # 2/3 haussiers
part_bear = [r for r in valid if r[4] == 2 and r[3] == 1]  # 2/3 baissiers
print(f"accords complets: haussier n={len(full_bull)} "
      f"(train {sum(1 for e in full_bull if e[5]=='train')} / "
      f"val {sum(1 for e in full_bull if e[5]=='val')}) | "
      f"baissier n={len(full_bear)} "
      f"(train {sum(1 for e in full_bear if e[5]=='train')} / "
      f"val {sum(1 for e in full_bear if e[5]=='val')})")
print(f"accords partiels 2/3: haussier n={len(part_bull)} "
      f"(train {sum(1 for e in part_bull if e[5]=='train')}/"
      f"val {sum(1 for e in part_bull if e[5]=='val')}) | "
      f"baissier n={len(part_bear)} "
      f"(train {sum(1 for e in part_bear if e[5]=='train')}/"
      f"val {sum(1 for e in part_bear if e[5]=='val')})")

def block(evs, side):
    """BLOC 24-72 : (driftL net, side net, brut) par split."""
    out = {}
    for sp in ["train", "val"]:
        sub = [e for e in evs if e[5] == sp]
        if not sub:
            out[sp] = None; continue
        Ls, Ss, Gs = [], [], []
        for h in HORIZONS:
            L = np.array([net_long(e[6][h][0]) for e in sub])
            G = np.array([e[6][h][0] for e in sub])
            S = np.array([net_short(e[6][h][0]) for e in sub])
            Ls.append(float(L.mean())); Ss.append(float(S.mean())); Gs.append(float(G.mean()))
        out[sp] = (float(np.mean(Ls)), float(np.mean(Ss)), float(np.mean(Gs)), len(sub))
    return out

for name, evs, side in [("ACCORD HAUSSIER (LONG=hypothèse)", full_bull, "long"),
                        ("ACCORD BAISSIER (SHORT=hypothèse)", full_bear, "short")]:
    print(f"\n── {name} ──")
    for sp in ["train", "val"]:
        sub = [e for e in evs if e[5] == sp]
        if not sub:
            print(f"  {sp}: 0 événement"); continue
        line = f"  {sp}: n={len(sub)}"
        Ls, Ss, Gs = [], [], []
        for h in HORIZONS:
            L = np.array([net_long(e[6][h][0]) for e in sub])
            G = np.array([e[6][h][0] for e in sub])
            S = np.array([net_short(e[6][h][0]) for e in sub])
            Ls.append(float(L.mean())); Ss.append(float(S.mean())); Gs.append(float(G.mean()))
            line += (f" | h{h} driftL {L.mean()*1e4:+.1f}bps (WR {100*np.mean(L>0):.1f}%)"
                     f" S {S.mean()*1e4:+.1f}bps")
        line += (f" || BLOC 24-72 driftL net {np.mean(Ls)*1e4:+.1f}bps "
                 f"SHORT net {np.mean(Ss)*1e4:+.1f}bps brut {np.mean(Gs)*1e4:+.1f}bps")
        print(line)

# ── gradient : complet vs partiel 2/3 (même sens de branche) ──
print("\n── GRADIENT complet 3/3 vs partiel 2/3 (BLOC, espérance de la branche, bps) ──")
grad = {}
for branch, evs_full, evs_part, side in [
        ("haussier (net LONG)", full_bull, part_bull, "L"),
        ("baissier (net SHORT)", full_bear, part_bear, "S")]:
    for sp in ["train", "val"]:
        f_ = block(evs_full, side)[sp]; p_ = block(evs_part, side)[sp]
        fv = (f_[0] if side == "L" else f_[1]) if f_ else float("nan")
        pv = (p_[0] if side == "L" else p_[1]) if p_ else float("nan")
        ok = (not np.isnan(fv)) and (not np.isnan(pv)) and fv > pv
        grad[(branch, sp)] = ok
        print(f"  {branch} {sp}: complet {fv*1e4:+.1f} vs partiel {pv*1e4:+.1f} "
              f"-> complet>partiel: {ok}")

# ── dépendance : runs d'accord consécutifs par symbole ──
runs = Counter(); maxrun = Counter()
for name, evs in [("bull", full_bull), ("bear", full_bear)]:
    for s in SYMBOLS:
        hrs = sorted(e[2] for e in evs if e[0] == s)
        r = 0; prev = None
        for t in hrs:
            r = r + 1 if (prev is not None and t - prev == 3600_000) else 1
            if r == 1:
                runs[name] += 1
            maxrun[(name, s)] = max(maxrun[(name, s)], r)
            prev = t
print("\n── dépendance (runs consécutifs) ──")
for name in ["bull", "bear"]:
    tot = sum(1 for e in (full_bull if name == "bull" else full_bear))
    mx = max([v for (n, s), v in maxrun.items() if n == name] or [0])
    print(f"  {name}: {tot} heures-événements, {runs[name]} runs distincts, run max={mx}h")

# ── BLOC STATS mensuel : wallet premier-arrivé (1 position/symbole, 1x, notionnel fixe) ──
print("\n── BLOC STATS mensuel (premier-arrivé par symbole, LONG/SHORT 1x 24h, notionnel fixe) ──")
ev_all = [(e, "long") for e in full_bull] + [(e, "short") for e in full_bear]
trades, last_exit = [], {}
for e, side in sorted(ev_all, key=lambda x: x[0][6]["entry_ts"]):
    s = e[0]
    if s in last_exit and e[6]["entry_ts"] <= last_exit[s]:
        continue
    r, exit_ts = e[6][24]
    net = net_long(r) if side == "long" else net_short(r)
    trades.append({"s": s, "side": side, "split": e[5], "entry_ts": e[6]["entry_ts"], "net": net})
    last_exit[s] = exit_ts
print(f"trades premier-arrivé: {len(trades)} (vs {len(ev_all)} événements bruts) "
      f"(long {sum(1 for t in trades if t['side']=='long')}/"
      f"short {sum(1 for t in trades if t['side']=='short')})")
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
print(f"  TOTAL: trades={len(trades)} WR_net={wr:.1f}% liqs=0 (1x par construction) "
      f"cumul={100*tot:+.2f}% ROI/an≈{100*tot/max(span_y,1e-9):+.1f}% DD={100*dd:.2f}% "
      f"record={best[0]} {best[3]:+.1f}% pire={worst[0]} {worst[3]:+.1f}% mois_nég={n_neg}/{len(rows_m)}")
print("  garde-fou composé-des-mois vs final: cumul des mois = cumul total par construction (notionnel fixe)")

# ── taux d'événements par symbole/split (honnêteté panel déséquilibré) ──
print("\n── taux d'événements par symbole/split (accords complets) ──")
cnt = Counter((e[0], e[5]) for e in full_bull + full_bear)
tot_sym = Counter((r[0], r[5]) for r in valid)
for s in SYMBOLS:
    tr, va = tot_sym[(s, "train")], tot_sym[(s, "val")]
    print(f"  {s:9s} train {cnt[(s,'train')]:5d}/{tr:6d} ({100*cnt[(s,'train')]/max(tr,1):4.1f}%) "
          f"val {cnt[(s,'val')]:5d}/{va:6d} ({100*cnt[(s,'val')]/max(va,1):4.1f}%)")

# ── VERDICT mécanique (critères pré-enregistrés) ──
print("\n── VERDICT (critères pré-enregistrés) ──")
nbt, nbv = len([e for e in full_bull if e[5] == "train"]), len([e for e in full_bull if e[5] == "val"])
nst, nsv = len([e for e in full_bear if e[5] == "train"]), len([e for e in full_bear if e[5] == "val"])
if nbt < 100 or nst < 100:
    print(f"SOUS-PUISANT (n train: bull={nbt}, bear={nst} < 100 par branche) — "
          f"non tranchable, pas un FAIL d'hypothèse")
else:
    def bloc(evs, sp, which):
        sub = [e for e in evs if e[5] == sp]
        Ls = [float(np.mean([net_long(e[6][h][0]) for e in sub])) for h in HORIZONS]
        Ss = [float(np.mean([net_short(e[6][h][0]) for e in sub])) for h in HORIZONS]
        return float(np.mean(Ls)) if which == "L" else float(np.mean(Ss))
    ok1 = all(bloc(full_bull, sp, "L") > 0 for sp in ["train", "val"])
    ok2 = all(bloc(full_bear, sp, "S") > 0 for sp in ["train", "val"])
    ok3 = all(grad[("haussier (net LONG)", sp)] and grad[("baissier (net SHORT)", sp)]
              for sp in ["train", "val"])
    # contrôle inverse : sur haussier le SHORT pire ; sur baissier le LONG pire
    c1 = all(bloc(full_bull, sp, "S") < bloc(full_bull, sp, "L") for sp in ["train", "val"])
    c2 = all(bloc(full_bear, sp, "L") < bloc(full_bear, sp, "S") for sp in ["train", "val"])
    ok4 = c1 and c2
    print(f"branch haussier LONG net > 0 (train {1e4*bloc(full_bull,'train','L'):+.1f} / "
          f"val {1e4*bloc(full_bull,'val','L'):+.1f} bps): {ok1}")
    print(f"branch baissier SHORT net > 0 (train {1e4*bloc(full_bear,'train','S'):+.1f} / "
          f"val {1e4*bloc(full_bear,'val','S'):+.1f} bps): {ok2}")
    print(f"gradient complet>partiel 2/3 (2 branches x 2 splits): {ok3}")
    print(f"contrôle inverse battu (haussier: S<L ; baissier: L<S, 2 splits): {ok4}")
    print("VERDICT: " + ("PASS — hypothèse validée (CANDIDATE, wallet séquentiel requis avant stack)"
                        if (ok1 and ok2 and ok3 and ok4)
                        else "FAIL — hypothèse réfutée (budget consommé, STOP)"))
