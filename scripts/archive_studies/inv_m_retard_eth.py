# INV-M — « LE RETARD D'ETH » — one-shot (une seule exécution, 2026-10-02)
# ARCHIVÉ (02/10/2026) — INV-M : FAIL, la structure cross-asset BTC/ETH ne délivre rien (docs/38)
# Pré-enregistrement : reports/aster/inv-m-retard-eth-2026-10.md
# Seal du gel : d2b8b846f90d9e44f358076097347d610b0699da572d0a197120193e02df223b
# DB en LECTURE SEULE (mode=ro). Aucun re-run de variante autorisé (docs/38).
import sqlite3
import numpy as np
import datetime as dt

DB = "file:data/warehouse/klines.db?mode=ro"
COST_RT = 0.0018  # 18 bps aller/retour
LAG_MAX = 0.4     # seuil unique gelé (le retard)

db = sqlite3.connect(DB, uri=True)
cur = db.cursor()
rows = cur.execute(
    "SELECT symbol, open_time, open, high, low, close FROM klines "
    "WHERE symbol IN ('BTCUSDT','ETHUSDT') AND interval='1h' ORDER BY open_time"
).fetchall()
db.close()

btc, eth = {}, {}
for s, ot, o, h, l, c in rows:
    (btc if s == "BTCUSDT" else eth)[ot] = (o, h, l, c)
common = sorted(ot for ot in btc if ot in eth)
assert all(b - a == 3600000 for a, b in zip(common, common[1:])), "grille non contigue"
n = len(common)
ts = np.array(common, dtype=np.int64)
btc_o = np.array([btc[t][0] for t in common])
btc_h = np.array([btc[t][1] for t in common])
btc_l = np.array([btc[t][2] for t in common])
btc_c = np.array([btc[t][3] for t in common])
eth_o = np.array([eth[t][0] for t in common])
eth_h = np.array([eth[t][1] for t in common])
eth_l = np.array([eth[t][2] for t in common])
eth_c = np.array([eth[t][3] for t in common])
print(f"grille commune n={n} {dt.datetime.utcfromtimestamp(ts[0]/1000)} -> {dt.datetime.utcfromtimestamp(ts[-1]/1000)} (ts_ms verifie)")

ret_btc = btc_c[1:] / btc_c[:-1] - 1.0
ret_eth = eth_c[1:] / eth_c[:-1] - 1.0
# index i sur les arrays ret_* correspond a la barre horaire commune i+1

split_i = int(np.floor(0.60 * n))  # borne : barres [0, split_i) = TRAIN
T_split = ts[split_i]
print(f"T_split = {dt.datetime.utcfromtimestamp(T_split/1000)} UTC (barres 0..{split_i-1} TRAIN / {split_i}..{n-1} VAL)")

# q95 de |ret1h BTC| sur TRAIN UNIQUEMENT (barres t >= 1 et t < split_i)
train_ret_btc = ret_btc[: split_i - 1]
q95 = float(np.quantile(np.abs(train_ret_btc), 0.95))
print(f"q95 TRAIN |ret1h BTC| = {q95*100:.4f} %  (n={len(train_ret_btc)})")

events = []
excl_beyond = 0
for i in range(1, n - 1):  # i = index horaire de la bougie BTC choc t (i>=1 pour ret defini)
    rb = ret_btc[i - 1]
    if abs(rb) < q95:
        continue
    split = "TRAIN" if i < split_i else "VAL"
    re_next = ret_eth[i]  # ret1h ETH sur la bougie t+1 (les 60 minutes suivantes)
    f = re_next * np.sign(rb) / abs(rb)
    j = i + 5  # sortie close_ETH(t+5)
    if j >= n:
        excl_beyond += 1
        continue
    entry = eth_c[i + 1]
    exit_ = eth_c[j]
    s = np.sign(rb)
    gross = s * (exit_ / entry - 1.0)
    net = gross - COST_RT
    # MAE sur la detention [t+1, t+5] : adverse pour LONG = (low-entry)/entry ; pour SHORT = (entry-high)/entry
    lows = eth_l[i + 1 : j + 1]
    highs = eth_h[i + 1 : j + 1]
    mae = float(np.min(lows) / entry - 1.0) if s > 0 else float(1.0 - np.max(highs) / entry)
    events.append(
        dict(i=i, split=split, ts=int(ts[i]), s=int(s), f=float(f), net=float(net),
             gross=float(gross), mae=mae, branch="HAUSSIERE" if s > 0 else "BAISSIERE")
    )

ev = events
n_tr = sum(1 for e in ev if e["split"] == "TRAIN")
n_va = len(ev) - n_tr
print(f"\nevenements retard (f<0.4) : n={len(ev)}  TRAIN={n_tr}  VAL={n_va}  exclus hors-grille={excl_beyond}")

def stats(sub, label):
    if not sub:
        print(f"  {label}: VIDE")
        return dict(n=0, wr=0.0, med=0.0, mean=0.0, suma=0.0)
    net = np.array([e["net"] for e in sub])
    gross = np.array([e["gross"] for e in sub])
    r = dict(n=len(sub), wr=float((net > 0).mean()), med=float(np.median(net)),
             mean=float(net.mean()), suma=float(net.sum()), medg=float(np.median(gross)))
    print(f"  {label}: n={r['n']} WR_net={r['wr']*100:.1f}% net med={r['med']*1e4:+.1f} bps (brut {r['medg']*1e4:+.1f}) mean={r['mean']*1e4:+.1f} somme={r['suma']*100:+.2f} %not")
    return r

print("\n== BLOCS BRANCHE x SPLIT (net, 18 bps RT) ==")
res = {}
for split in ("TRAIN", "VAL"):
    for br in ("HAUSSIERE", "BAISSIERE", "ALL"):
        sub = [e for e in ev if e["split"] == split and (br == "ALL" or e["branch"] == br)]
        res[(split, br)] = stats(sub, f"{split:5s} {br:10s}")

print("\n== CONTROLE INVERSE (f<0 divergence continue) vs ensemble (f<0.4) ==")
ctrl = {}
for split in ("TRAIN", "VAL"):
    sub_c = [e for e in ev if e["split"] == split and e["f"] < 0]
    ctrl[split] = stats(sub_c, f"{split:5s} CONTROLE f<0")
    sub_pur = [e for e in ev if e["split"] == split and 0 <= e["f"] < LAG_MAX]
    stats(sub_pur, f"{split:5s} RETARD PUR 0<=f<0.4")

print("\n== GRADIENT ampleur du retard : quintiles de f (retards purs 0<=f<0.4, TRAIN) ==")
pur_tr = [e for e in ev if e["split"] == "TRAIN" and 0 <= e["f"] < LAG_MAX]
qs = np.quantile([e["f"] for e in pur_tr], [0.2, 0.4, 0.6, 0.8]) if len(pur_tr) >= 5 else []
monotone_med, c4 = [], False
for qi in range(5):
    lo = 0.0 if qi == 0 else qs[qi - 1]
    hi = LAG_MAX if qi == 4 else qs[qi]
    sub = [e for e in pur_tr if (e["f"] >= lo if qi == 0 else e["f"] > lo) and e["f"] <= hi]
    sub_va = [e for e in ev if e["split"] == "VAL" and 0 <= e["f"] < LAG_MAX and
              (e["f"] >= lo if qi == 0 else e["f"] > lo) and e["f"] <= hi]
    m_tr = np.median([e["net"] for e in sub]) * 1e4 if sub else float("nan")
    m_va = np.median([e["net"] for e in sub_va]) * 1e4 if sub_va else float("nan")
    monotone_med.append(m_tr)
    print(f"  Q{qi+1} f in ({lo:+.3f},{hi:+.3f}] TRAIN n={len(sub)} med_net={m_tr:+.1f} bps | VAL n={len(sub_va)} med={m_va:+.1f}")
if len(pur_tr) >= 5:
    inversions = sum(1 for a, b in zip(monotone_med, monotone_med[1:]) if b > a + 1e-12)
    min_q = min(len([e for e in pur_tr if (e["f"] >= (0.0 if q == 0 else qs[q-1]) and e["f"] <= (LAG_MAX if q == 4 else qs[q]))]) for q in range(5))
    c4 = inversions == 0 and min_q >= 5
    print(f"  C4 GRADIENT : inversions={inversions} min_n/quintile={min_q} -> {'OK monotone' if c4 else 'ECHEC'}")

print("\n== WALLET SEQUENTIEL premier-arrive (1 position ETH a la fois, 1x, compounding, branches fusionnees) ==")
ev_sorted = sorted(ev, key=lambda e: e["i"])
wallet, busy_until, bal = [], -1, 1.0
for e in ev_sorted:
    entry_i, exit_i = e["i"] + 1, e["i"] + 5
    if entry_i <= busy_until:
        continue
    busy_until = exit_i
    pnl = bal * e["net"]
    bal += pnl
    wallet.append(dict(e, pnl=pnl, bal=bal))
print(f"wallet trades={len(wallet)} (chevauchements sautes={len(ev_sorted)-len(wallet)}) cumul={(bal-1)*100:+.2f} %")
mae_max = min(e["mae"] for e in ev) if ev else 0.0
print(f"MAE max detention = {mae_max*100:.2f} %  -> levier sûr <= {100/(abs(mae_max)*100+0.5):.1f}x (trade a 1x : 0 liq)")
liq = sum(1 for e in ev if e["mae"] <= -1.0)
print(f"trades a MAE<=-100% (liq a 1x) : {liq}")

print("\n== BLOC STATS MENSUEL (wallet, branches fusionnees) ==")
mois = {}
for w in wallet:
    m = dt.datetime.utcfromtimestamp(ts[w["i"]] / 1000).strftime("%Y-%m")
    mois.setdefault(m, []).append(w)
cum = 1.0
print(f"{'mois':7s} {'sp':5s} {'n_ev':>4s} {'n_wal':>5s} {'WR':>6s} {'med_bps':>8s} {'wal%':>8s} {'cum%':>9s}")
for m in sorted(mois):
    ws = mois[m]
    ev_m = [e for e in ev if dt.datetime.utcfromtimestamp(ts[e["i"]] / 1000).strftime("%Y-%m") == m]
    med = np.median([e["net"] for e in ev_m]) * 1e4
    wr = (np.array([e["net"] for e in ws]) > 0).mean() * 100
    mret = (ws[-1]["bal"] / (ws[0]["bal"] - sum(x["pnl"] for x in ws)) - 1) * 100
    cum *= 1 + mret / 100
    sp = "TRAIN" if ws[0]["i"] < split_i else "VAL"
    print(f"{m:7s} {sp:5s} {len(ev_m):4d} {len(ws):5d} {wr:5.1f}% {med:+8.1f} {mret:+8.2f} {(cum-1)*100:+9.2f}")

print("\n== VERDICT (critères pré-enregistrés) ==")
c4_grad = c4
ok_n = n_tr >= 60
c2 = res[("TRAIN","HAUSSIERE")]["med"] > 0 and res[("VAL","HAUSSIERE")]["med"] > 0
c3 = res[("TRAIN","BAISSIERE")]["med"] > 0 and res[("VAL","BAISSIERE")]["med"] > 0
c5 = ctrl["TRAIN"]["med"] < res[("TRAIN","ALL")]["med"] and ctrl["VAL"]["med"] < res[("VAL","ALL")]["med"]
print(f"C1 n_train>=60 : {'OK' if ok_n else 'ECHEC'} (n={n_tr})")
print(f"C2 haussiere net>0 TR+VA : {'OK' if c2 else 'ECHEC'}")
print(f"C3 baissiere net>0 TR+VA : {'OK' if c3 else 'ECHEC'}")
print(f"C4 gradient quintiles : {'OK' if c4_grad else 'ECHEC'} (non croissant Q1->Q5, >=5/quintile)")
print(f"C5 controle battu TR+VA : {'OK' if c5 else 'ECHEC'} (ctrl TR {ctrl['TRAIN']['med']*1e4:+.1f} vs all {res[('TRAIN','ALL')]['med']*1e4:+.1f} | VA {ctrl['VAL']['med']*1e4:+.1f} vs {res[('VAL','ALL')]['med']*1e4:+.1f})")
