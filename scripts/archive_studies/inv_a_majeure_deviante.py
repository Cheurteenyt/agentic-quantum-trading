# INV-A — LA MAJEURE DÉVIANTE (one-shot, pré-enregistré 2026-10-02, tag freeze-2026-10-02)
# ARCHIVÉ (02/10/2026) — INV-A : FAIL hypothèse réfutée (docs/38, budget consommé)
# Gouvernance : docs/38-gouvernance-recherche.md · budget : 1 expérience, zéro itération.
# Pré-enregistrement complet : reports/aster/inv-a-majeure-deviante-2026-10.md (Partie 1 gelée AVANT exécution,
#   sha256 fichier à l'écriture = 0a59f1651e169c110c6198cc085a3dbd843cdc43b077f41bdcfe19421b0c21bc).
# DB en LECTURE SEULE (mode=ro). Aucun indicateur réemployé : inputs = closes 1h bruts.
import sqlite3
import os
import numpy as np

TRAIN_ONLY = os.environ.get("INV_TRAIN_ONLY") == "1"  # val jamais regardée avant le verdict train

DB = "file:/run/media/cheurteen/Jeux SSD/trading-agent/data/warehouse/klines.db?mode=ro"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
Z_THR = 2.0          # SEUL seuil pré-déclaré
ROB_THR = 2.2        # variante de robustesse unique (train only, info)
COST = 0.0036        # 36 bps RT par paire (2 jambes taker 18 bps)
H_PRIM, HOURS = 48, [24, 48, 72]   # 48h primaire ; 24/72h contexte pré-déclaré
SPLIT_FRAC = 0.60    # 60/40 chrono GLOBAL
PANEL_START = 1758664800000  # 2025-09-23 22:00 UTC (début commun BNB/DOGE)

con = sqlite3.connect(DB, uri=True)
closes, opens, times = {}, {}, None
for s in SYMS:
    rows = con.execute(
        "SELECT open_time, close, open FROM klines WHERE symbol=? AND interval='1h' AND open_time>=? ORDER BY open_time",
        (s, PANEL_START)).fetchall()
    times_ = np.array([r[0] for r in rows], dtype=np.int64)
    closes[s] = dict(zip(times_.tolist(), [r[1] for r in rows]))
    opens[s] = dict(zip(times_.tolist(), [r[2] for r in rows]))
    if times is None or len(times_) < len(times):
        times = times_
con.close()

# grille commune : heures présentes chez les 6
common = np.array([t for t in times if all(t in closes[s] for s in SYMS)], dtype=np.int64)
C = np.column_stack([[closes[s][t] for t in common] for s in SYMS])  # (T, 6) closes
O = np.column_stack([[opens[s][t] for t in common] for s in SYMS])   # (T, 6) opens

ret24 = np.full_like(C, np.nan)
ret24[24:] = C[24:] / C[:-24] - 1.0
med = np.nanmedian(np.where(np.isnan(ret24), np.nan, ret24), axis=1)
sd = np.nanstd(ret24, axis=1, ddof=1)
with np.errstate(invalid="ignore", divide="ignore"):
    Z = (ret24 - med[:, None]) / sd[:, None]

# forward returns open(t+1) -> open(t+1+H) : VRAIS opens (convention docs/38, pas d'approximation)
events = []
for k in range(24, len(common)):
    t = common[k]
    for j, s in enumerate(SYMS):
        z = Z[k, j]
        if not np.isfinite(z) or abs(z) < Z_THR:
            continue
        k_out = k + 1 + max(HOURS)
        if k_out >= len(common):
            continue
        fwd = {}
        ok = True
        for H in HOURS:
            entry = O[k + 1, :]                       # opens t+1 pour les 6
            exitp = O[k + 1 + H, :]                   # opens t+1+H pour les 6
            if np.any(np.isnan(entry)) or np.any(np.isnan(exitp)) or np.any(entry <= 0) or np.any(exitp <= 0):
                ok = False
                break
            fwd[H] = exitp / entry - 1.0              # ret 0->H pour les 6
        if not ok:
            continue
        evs = {"t": int(t), "sym": s, "z": float(z), "sign": 1 if z >= Z_THR else -1, "fwd": fwd}
        events.append(evs)

# frontière pré-déclarée : fenêtre d'événements [PANEL_START+24h , dernière heure évaluable à 72h], 60 % chrono
t_start = int(PANEL_START + 24 * 3600 * 1000)
t_end = int(common[-1] - 72 * 3600 * 1000)
split = t_start + int(SPLIT_FRAC * (t_end - t_start))
print(f"PANEL common hours={len(common)} events={len(events)} "
      f"window=[{t_start}->{t_end}] split={split}")

def pnl(e, H, inv=False):
    r = e["fwd"][H]
    pack_med = float(np.median(r))
    spread = pack_med - r[SYMS.index(e["sym"])]        # réversion : short déviante-haut / long déviante-bas
    gross = -spread if e["sign"] < 0 else spread       # déviante-bas : long i vs pack => spread inversé
    if inv:
        gross = -gross                                  # contrôle : continuation
    return gross - COST

def stats(evs, H, inv=False):
    if not evs:
        return None
    p = np.array([pnl(e, H, inv) for e in evs])
    return {"n": len(p), "mean": p.mean(), "wr": (p > 0).mean(), "sum": p.sum(),
            "med": float(np.median(p)), "p05": float(np.percentile(p, 5)), "p95": float(np.percentile(p, 95))}

def terciles(evs, H, inv=False):
    zs = np.array([abs(e["z"]) for e in evs])
    q1, q2 = np.quantile(zs, [1 / 3, 2 / 3])
    out = []
    for name, m in [("T1", zs <= q1), ("T2", (zs > q1) & (zs <= q2)), ("T3", zs > q2)]:
        sub = [e for e, mm in zip(evs, m) if mm]
        st = stats(sub, H, inv)
        out.append((name, st))
    return out

train = [e for e in events if e["t"] + 72 * 3600 * 1000 <= split]
val = [e for e in events if e["t"] >= split]
purged = len(events) - len(train) - len(val)
print(f"train n={len(train)} val n={len(val)} purged={purged} split={split}")

import datetime as dt
def month_key(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m")

def monthly(evs, H, inv=False):
    out = {}
    for e in evs:
        out.setdefault(month_key(e["t"]), []).append(pnl(e, H, inv))
    return {m: {"n": len(v), "wr": float(np.mean(np.array(v) > 0)), "sum_bps": float(np.sum(v) * 1e4),
                "mean_bps": float(np.mean(v) * 1e4)} for m, v in sorted(out.items())}

def block(name, evs, H, inv=False):
    st = stats(evs, H, inv)
    if st is None:
        print(f"{name}: n=0"); return
    print(f"{name}: n={st['n']} mean={st['mean']*1e4:+.1f}bps wr={st['wr']*100:.1f}% "
          f"med={st['med']*1e4:+.1f} p05={st['p05']*1e4:+.0f} p95={st['p95']*1e4:+.0f}")
    for name_t, stt in terciles(evs, H, inv):
        if stt:
            print(f"  {name_t} |z| mean={stt['mean']*1e4:+.1f}bps n={stt['n']} wr={stt['wr']*100:.0f}%")
    mm = monthly(evs, H, inv)
    sums = [v["sum_bps"] for v in mm.values()]
    print(f"  months: {len(mm)} neg={sum(1 for s in sums if s < 0)} worst={min(sums):+.0f} best={max(sums):+.0f}")
    for m, v in mm.items():
        print(f"    {m}: n={v['n']} wr={v['wr']*100:.0f}% sum={v['sum_bps']:+.0f}bps mean={v['mean_bps']:+.1f}")

for H in HOURS:
    tag = "PRIMAIRE" if H == H_PRIM else "contexte"
    print(f"\n=== H={H}h ({tag}) — REVERSION ===")
    block("TRAIN", train, H)
    if not TRAIN_ONLY:
        block("VAL  ", val, H)
    print(f"--- H={H}h — CONTRÔLE INVERSE (continuation) ---")
    block("TRAIN-inv", train, H, inv=True)
    if not TRAIN_ONLY:
        block("VAL-inv  ", val, H, inv=True)

print("\n=== signes séparés (H=48, reversion, net) ===")
for lab, sub in [("haut z>=+2", [e for e in events if e["sign"] > 0]),
                 ("bas  z<=-2", [e for e in events if e["sign"] < 0])]:
    tr = [e for e in sub if e in train]
    str_ = stats(tr, 48)
    line = f"{lab}: train n={str_['n']} mean={str_['mean']*1e4:+.1f}bps wr={str_['wr']*100:.0f}%"
    if not TRAIN_ONLY:
        vl = [e for e in sub if e in val]
        svl = stats(vl, 48)
        line += f" | val n={svl['n']} mean={svl['mean']*1e4:+.1f}bps wr={svl['wr']*100:.0f}%"
    print(line)

print("\n=== robustesse unique : |z|>=2.2, train, H=48 (info, pas un second seuil) ===")
rb = [e for e in train if abs(e["z"]) >= ROB_THR]
block("TRAIN-2.2", rb, 48)

print("\n=== répartition par symbole (tous événements) ===")
for s in SYMS:
    sub = [e for e in events if e["sym"] == s]
    print(f"  {s}: n={len(sub)} (haut {sum(1 for e in sub if e['sign']>0)} / bas {sum(1 for e in sub if e['sign']<0)})")
multi = {}
for e in events:
    multi[e["t"]] = multi.get(e["t"], 0) + 1
print(f"heures a plusieurs deviantes: {sum(1 for v in multi.values() if v > 1)} / {len(multi)} heures événement")
