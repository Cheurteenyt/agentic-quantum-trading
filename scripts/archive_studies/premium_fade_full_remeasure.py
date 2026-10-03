# ARCHIVÉ (03/10) — verdict NUL rendu au registre docs/20 ; le test listing de lundi est un one-shot nouveau (research/hypotheses/premium-fade-listing.md)
# Re-mesure DÉFINITIVE du premium fade sur le dataset 15m complet (367 symboles × 5 ans).
# Contexte : le chiffre orphelin « 87 % WR, +21 %/an @ 3,33x » n'existe dans AUCUN code
# committé — loi du registre : non reproductible = mort. Ce script EST la reproductibilité.
#
# CONFIG GELÉE AVANT MESURE (pré-enregistrement, zéro scan de paramètres) :
#   - Data      : premium_15m (premium_close), tous symboles ≥ 5000 barres
#   - Signal    : z = (prem - roll_mean96) / roll_std96 ; tir si |z| ≥ 2.0
#   - Direction : fade = -sign(z) (premium riche → short, pauvre → long)
#   - Exécution : entrée premium_open[t+1] (le prix exécutable après le signal,
#                 zéro look-ahead), sortie premium_close[t+H], H = 4 barres (1 h)
#   - Non-overlap : par symbole, le prochain tir ≥ t+H+1
#   - Coûts     : 8 bps RT (4 jambes taker du trade de base spot+perp)
#   - Split     : temporel 70/30 sur la plage globale (jamais aléatoire)
#   - Naked     : check secondaire sur les 19 symboles qui ont les klines perp 15m
#
# CRITÈRES PASS ÉCRITS AVANT DE VOIR LE RÉSULTAT :
#   P1 WR_train ≥ 65 % ET WR_val ≥ 60 % (net 8 bps)
#   P2 espérance nette VAL > 0 bps/trade
#   P3 contrôle inverse (direction = +sign(z)) : espérance VAL < espérance signal
#   P4 gradient |z| : [|2,3) < |z|≥3] en espérance (monotone croissant)
#   P5 BLOC STATS mensuel : ≥ 60 % de mois positifs (période commune train+val)
#   FAIL si P1-P3 quelconque échoue → le chiffre orphelin meurt au registre.

import sqlite3
import sys
import numpy as np
import pandas as pd

# Grille PRÉ-DÉCLARÉE (audit du claim orphelin, zéro scan post-hoc) :
#   cell universe : tous symboles, W=96, H=4, z incluant la barre courante
#   cell replica  : BTC+ETH+SOL (la config exacte du claim mémoire), W=20,
#                   z EXCLUANT la barre courante (forme enregistrée par Bonsai),
#                   hold 1h ET 24h (les 2 horizons présents dans le dossier)
ARGS = dict(a.split("=") for a in sys.argv[1:] if "=" in a)
CELL = ARGS.get("cell", "universe")
SYMS_REPLICA = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
if CELL == "replica":
    W, Z_TH, EXCL_CUR = 20, 2.0, True
    H = int(ARGS.get("h", "4"))
else:
    W, Z_TH, H, EXCL_CUR = 96, 2.0, 4, False
COST_BPS = 8.0
MIN_BARS = 5000

DB = "data/warehouse/klines.db"

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
df = pd.read_sql_query(
    "SELECT symbol, open_time, premium_open, premium_close FROM premium_15m",
    con)
con.close()
df["symbol"] = df["symbol"].astype("category")
df = df.sort_values(["symbol", "open_time"]).reset_index(drop=True)

counts = df.groupby("symbol", observed=True)["open_time"].count()
keep = counts[counts >= MIN_BARS].index
if CELL == "replica":
    keep = [s for s in SYMS_REPLICA if s in set(keep)]
df = df[df["symbol"].isin(keep)].reset_index(drop=True)
syms = df["symbol"].unique()
t_min, t_max = df["open_time"].min(), df["open_time"].max()
cutoff = t_min + 0.70 * (t_max - t_min)
print(f"CELL={CELL} W={W} H={H} z_hors_barre={EXCL_CUR} | syms={len(syms)}  barres={len(df):,}  "
      f"plage={pd.Timestamp(t_min, unit='ms').date()} → {pd.Timestamp(t_max, unit='ms').date()}")
print(f"split temporel 70/30 à {pd.Timestamp(cutoff, unit='ms').date()}\n")

rows = []  # un dict par trade
for s, g in df.groupby("symbol", observed=True, sort=False):
    prem = g["premium_close"].to_numpy()
    open_ = g["premium_open"].to_numpy()
    ts = g["open_time"].to_numpy()
    n = len(g)
    r = pd.Series(prem)
    if EXCL_CUR:  # la forme du claim : fenêtre sur les 20 barres PRÉCÉDENTES
        mu = r.shift(1).rolling(W, min_periods=W).mean().to_numpy()
        sd = r.shift(1).rolling(W, min_periods=W).std().to_numpy()
    else:
        mu = r.rolling(W, min_periods=W).mean().to_numpy()
        sd = r.rolling(W, min_periods=W).std().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (prem - mu) / sd
    cand = np.where(np.abs(z) >= Z_TH)[0]
    last = -10**9
    for i in cand:
        if i <= last + H or i + 1 + H >= n:
            continue
        last = i
        d = -np.sign(z[i])
        entry, exit_ = open_[i + 1], prem[i + H]
        pnl = d * (exit_ - entry) * 1e4 - COST_BPS
        win_close = prem[i + 1: i + H + 1]
        mae = (win_close - entry).max() if d < 0 else (entry - win_close).min()
        rows.append((s, ts[i + 1], z[i], d, pnl, -pnl - 2 * COST_BPS, max(mae, 0.0) * 1e4, entry))

tr = pd.DataFrame(rows, columns=["symbol", "ts", "z", "dir", "pnl_bps",
                                 "pnl_inv_bps", "mae_prem_bps", "entry_prem"])
tr["side"] = np.where(tr["dir"] > 0, "LONG", "SHORT")
tr["period"] = np.where(tr["ts"] < cutoff, "TRAIN", "VAL")
tr["month"] = pd.to_datetime(tr["ts"], unit="ms").dt.to_period("M").astype(str)
tr["bucket"] = np.where(np.abs(tr["z"]) >= 3.0, "|z|>=3", "2<=|z|<3")
print(f"trades={len(tr):,}  (LONG {(tr['dir']>0).sum():,} / SHORT {(tr['dir']<0).sum():,})")

def bloc(sub, label):
    if len(sub) == 0:
        return f"{label}: vide"
    m = sub.groupby("month")["pnl_bps"].sum()
    cum = m.cumsum()
    dd = (cum - cum.cummax()).min()
    return (f"{label}: n={len(sub):,} WR={(sub['pnl_bps']>0).mean()*100:.1f}% "
            f"esp={sub['pnl_bps'].mean():+.2f} bps/trade | mois {len(m)} "
            f"(+{(m>0).sum()}/-{(m<=0).sum()} = {(m>0).mean()*100:.0f}% pos) "
            f"DD {dd:+.0f} bps record {cum.max():+.0f} bps")

print("\n== BLOC STATS (hedged, net 8 bps) ==")
for per in ("TRAIN", "VAL"):
    print(bloc(tr[tr["period"] == per], per))

print("\n== CRITÈRES PRÉ-ENREGISTRÉS ==")
vt = tr[tr["period"] == "TRAIN"]; vv = tr[tr["period"] == "VAL"]
wr_t, wr_v = (vt["pnl_bps"] > 0).mean() * 100, (vv["pnl_bps"] > 0).mean() * 100
esp_v = vv["pnl_bps"].mean(); esp_inv = vv["pnl_inv_bps"].mean()
g23 = vv[vv["bucket"] == "2<=|z|<3"]["pnl_bps"].mean()
g3p = vv[vv["bucket"] == "|z|>=3"]["pnl_bps"].mean()
mm = tr.groupby("month")["pnl_bps"].sum()
p5 = (mm > 0).mean() * 100
checks = [
    ("P1 WR train/val >= 65/60", wr_t >= 65 and wr_v >= 60, f"{wr_t:.1f}% / {wr_v:.1f}%"),
    ("P2 espérance VAL > 0", esp_v > 0, f"{esp_v:+.2f} bps"),
    ("P3 inverse pire que signal", esp_inv < esp_v, f"inv {esp_inv:+.2f} vs {esp_v:+.2f}"),
    ("P4 gradient |z|>=3 > [2,3)", g3p > g23, f"{g23:+.2f} → {g3p:+.2f}"),
    ("P5 >= 60% mois positifs", p5 >= 60, f"{p5:.0f}%"),
]
for name, ok, val in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {name:32s} {val}")
verdict = "VALIDÉ" if all(ok for _, ok, _ in checks[:3]) and sum(ok for _, ok, _ in checks) >= 4 else "FAIL"
print(f"\nVERDICT GLOBAL: {verdict}")

print("\n== MAE / LEVIER 0-LIQ (lev <= 100/(maxMAE% + 0.5)) ==")
for per in ("TRAIN", "VAL"):
    mae_pct = tr[tr["period"] == per]["mae_prem_bps"].max() / 100
    lev = 100 / (mae_pct + 0.5) if mae_pct > 0 else float("inf")
    n_yr = len(tr[tr["period"] == per]) / ((t_max - t_min) / 3.15576e10 * (0.3 if per == "VAL" else 0.7))
    ann_1x = tr[tr["period"] == per]["pnl_bps"].mean() * n_yr / 1e4
    print(f"  {per}: maxMAE premium {mae_pct:.3f}% → lev {min(lev, 50):.1f}x | "
          f"{n_yr:.0f} trades/an | {ann_1x*100:+.1f}%/an @1x → {ann_1x*min(lev,50)*100:+.0f}%/an @lev")

# Naked (check de réalité, 19 syms avec perp 15m)
k = pd.read_sql_query(
    "SELECT symbol, open_time, open, high, low, close FROM klines WHERE interval='15m'", con := sqlite3.connect(f"file:{DB}?mode=ro", uri=True))
con.close()
k = k[k["symbol"].isin(set(tr["symbol"]))].set_index(["symbol", "open_time"]).sort_index()
idx = k.index.intersection(pd.MultiIndex.from_arrays([tr["symbol"], tr["ts"]]))
sub = tr.set_index(["symbol", "ts"]).loc[idx].reset_index()
kk = k.loc[idx]
ret = kk["close"].to_numpy() / kk["open"].to_numpy() - 1
pnl_naked = sub["dir"].to_numpy() * ret * 1e4 - COST_BPS
mae_px = np.where(sub["dir"] < 0, (kk["high"] - kk["open"]) / kk["open"],
                  (kk["open"] - kk["low"]) / kk["open"]).max()
print(f"\n== NAKED PERP (check réalité, {sub['symbol'].nunique()} syms 15m) ==")
print(f"  n={len(sub)} WR={(pnl_naked>0).mean()*100:.1f}% esp={pnl_naked.mean():+.1f} bps "
      f"| maxMAE prix {mae_px*100:.2f}% → lev 0-liq {100/(mae_px*100+0.5):.2f}x")
