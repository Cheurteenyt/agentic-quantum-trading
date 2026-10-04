# premium_fade_listing_test.py — L'ÉVALUATEUR du test pré-enregistré du lundi 05/10.
# Hypothèse + critères : research/hypotheses/premium-fade-listing.md (RIGIDES, non modifiables).
#
# FLUX OBLIGATOIRE (gouvernance) :
#   1. lun 05/10 : .venv/bin/python scripts/lab_ledger.py check --family premium \
#        --strategy premium_fade_listing --hypothesis "fade listing <90j avec discriminateur Δindex"
#   2. si exit 0 → CE script ; verdict → lab_ledger log (P5 KILL = FAIL, pas d'appel).
#   3. JAMAIS de run sur données réelles avant le gate (ce fichier est l'évaluateur, pas l'expérience).
#
# AMENDEMENT DATÉ (03/10, AVANT tout run, l'intention inchangée) : le discriminateur
# pré-enregistré dérivait Δindex au premier ordre (Δperp − Δpremium) faute de klines perp 15m ;
# elles existent depuis la prep du 03/10 (352 syms) → la formule EXACTE index_t = perp_t/(1+prem_t)
# devient la primaire, le premier ordre reste en colonne de sensibilité. Le seuil 0,5 % ne bouge pas.
#
# Mode smoke (données synthétiques, aucune DB) : .venv/bin/python scripts/studies/premium_fade_listing_test.py --smoke

import argparse
import sqlite3
import sys
import numpy as np
import pandas as pd

DB = "data/warehouse/klines.db"
W, Z_TH, H, COST_BPS = 96, 2.0, 4, 8.0
AGE_MAX_J = 90
AGE_BANDS = [("0-7j", 0, 7), ("7-30j", 7, 30), ("30-90j", 30, 90)]
IDX_TH = 0.005      # |Δindex 15m| ≤ 0,5 % = trade valide (théorie adversariale, pas nos données)
KILL_RATE = 0.15    # KILL si > 15 % de toxiques


def build_trades(po, pc, ts, kop, kcl, first_bar):
    """Une passe numpy par symbole → DataFrame des trades listing.

    po/pc : premium_open/close ; ts : open_time (ms) ; kop/kcl : perp 15m alignés
    sur les MÊMES indices (np.nan où la kline manque) ; first_bar : ms du listing (proxy).
    """
    n = len(po)
    r = pd.Series(pc)
    mu = r.rolling(W, min_periods=W).mean().to_numpy()
    sd = r.rolling(W, min_periods=W).std().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (pc - mu) / sd
    cand = np.where(np.abs(z) >= Z_TH)[0]
    out = []
    last = -10**9
    for i in cand:
        if i <= last + H or i + 1 + H >= n:
            continue
        last = i
        if np.isnan(kop[i]) or np.isnan(kcl[i]) or kop[i] <= 0:
            continue  # kline perp manquante → trade non évaluable (compté à part)
        d = -np.sign(z[i])
        entry, exit_ = po[i + 1], pc[i + H]
        # discriminateur : Δindex EXACT sur la bougie signal (index = perp/(1+prem))
        idx_open = kop[i] / (1.0 + po[i]) if (1.0 + po[i]) > 0 else np.nan
        idx_close = kcl[i] / (1.0 + pc[i]) if (1.0 + pc[i]) > 0 else np.nan
        if np.isnan(idx_open) or np.isnan(idx_close) or idx_open <= 0:
            continue
        d_index = idx_close / idx_open - 1.0
        d_index_fo = (kcl[i] / kop[i] - 1.0) - (pc[i] - po[i])  # premier ordre (sensibilité)
        win = pc[i + 1: i + H + 1]
        mae = (win - entry).max() if d < 0 else (entry - win).min()
        out.append((ts[i + 1], z[i], d, entry, exit_, max(mae, 0.0) * 1e4,
                    d_index, d_index_fo, d * (exit_ - entry) * 1e4 - COST_BPS,
                    -d * (exit_ - entry) * 1e4 - COST_BPS))
    cols = ["ts", "z", "dir", "entry", "exit", "mae_prem_bps",
            "d_index", "d_index_fo", "pnl_bps", "pnl_inv_bps"]
    if not out:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(out, columns=cols)
    df["age_j"] = (df["ts"] - first_bar) / 864e5
    df = df[df["age_j"] < AGE_MAX_J].copy()
    df["band"] = pd.cut(df["age_j"], bins=[-0.1, 7, 30, 90], labels=[b for b, _, _ in AGE_BANDS])
    df["valid"] = df["d_index"].abs() <= IDX_TH
    return df


def judge(tr, cutoff):
    """Les 6 critères pré-enregistrés. tr = trades listing (toutes validités)."""
    tr["period"] = np.where(tr["ts"] < cutoff, "TRAIN", "VAL")
    v = tr[tr["valid"]].copy()
    checks, kill = [], False

    toxic_rate = 1.0 - tr["valid"].mean()
    p5 = toxic_rate <= KILL_RATE
    kill = not p5
    checks.append(("P5 discrim.: toxiques <= 15%", p5, f"{toxic_rate*100:.1f}% toxiques "
                   f"(FO: {(1.0 - (tr['d_index_fo'].abs() <= IDX_TH).mean())*100:.1f}%)"))

    vt, vv = v[v["period"] == "TRAIN"], v[v["period"] == "VAL"]
    if len(vt) and len(vv):
        wr_t, wr_v = (vt["pnl_bps"] > 0).mean() * 100, (vv["pnl_bps"] > 0).mean() * 100
        esp_v = vv["pnl_bps"].mean()
        checks.append(("P1 WR valides train/val >= 65/60", wr_t >= 65 and wr_v >= 60,
                       f"{wr_t:.1f}% / {wr_v:.1f}% (n {len(vt):,}/{len(vv):,})"))
        checks.append(("P2 espérance VAL > +2 bps", esp_v > 2.0, f"{esp_v:+.2f} bps"))
        checks.append(("P3 inverse pire", vv["pnl_inv_bps"].mean() < esp_v,
                       f"inv {vv['pnl_inv_bps'].mean():+.2f} vs {esp_v:+.2f}"))
        esp_by_band = vv.groupby("band", observed=True)["pnl_bps"].mean()
        ok4 = all(esp_by_band.get(a, -1e9) >= esp_by_band.get(b, 1e9) for a, b in
                  [("0-7j", "7-30j"), ("7-30j", "30-90j")])
        checks.append(("P4 gradient d'âge monotone VAL", ok4,
                       " → ".join(f"{b}:{esp_by_band.get(b, float('nan')):+.1f}" for b, _, _ in AGE_BANDS)))
        mm = v.groupby(pd.to_datetime(v["ts"], unit="ms").dt.to_period("M"))["pnl_bps"].sum()
        p6 = (mm > 0).mean() * 100
        checks.append(("P6 >= 60% mois positifs", p6 >= 60, f"{p6:.0f}% ({len(mm)} mois, "
                       f"DD {(mm.cumsum()-mm.cumsum().cummax()).min():+.0f} bps)"))
    verdict = "KILL (P5)" if kill else ("VALIDÉ" if sum(o for _, o, _ in checks) == len(checks) else "FAIL")
    return checks, verdict


def smoke():
    """Self-test synthétique : le premium spike SANS mouvement d'index doit être valide."""
    n = 400
    ts = 1_700_000_000_000 + np.arange(n) * 900_000
    rng = np.random.default_rng(501)
    idx = 100 * np.exp(np.cumsum(rng.normal(0, 0.0002, n)))          # index calme
    prem = np.zeros(n)
    prem[100] = 0.05                                                  # spike 5 %, index immobile
    prem[100:104] += np.linspace(0.05, 0.02, 4)                       # reversion partielle
    prem += rng.normal(0, 0.0005, n)
    perp = idx * (1 + prem)
    po, pc = prem, np.roll(prem, -1); pc[-1] = prem[-1]
    kop, kcl = perp, np.roll(perp, -1); kcl[-1] = perp[-1]
    tr = build_trades(po, pc, ts, kop, kcl, ts[0])
    assert len(tr) >= 1, "smoke: aucun trade"
    t = tr.iloc[0]
    assert t["valid"], f"smoke: trade devrait être valide (Δindex={t['d_index']:.4%})"
    assert t["dir"] < 0, "smoke: premium spike positif → short attendu"
    print(f"SMOKE OK : {len(tr)} trade(s), Δindex={t['d_index']:.4%} (≤0,5 %), "
          f"dir={'SHORT' if t['dir']<0 else 'LONG'}, pnl={t['pnl_bps']:+.1f} bps")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    if a.smoke:
        return smoke()

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    prem = pd.read_sql_query(
        "SELECT symbol, open_time, premium_open, premium_close FROM premium_15m", con)
    kl = pd.read_sql_query(
        "SELECT symbol, open_time, open, close FROM klines WHERE interval='15m'", con)
    con.close()
    prem["symbol"] = prem["symbol"].astype("category")
    prem = prem.sort_values(["symbol", "open_time"]).reset_index(drop=True)
    counts = prem.groupby("symbol", observed=True)["open_time"].count()
    prem = prem[prem["symbol"].isin(counts[counts >= W + H + 2].index)].reset_index(drop=True)
    kmap = {s: g.set_index("open_time")[["open", "close"]]
            for s, g in kl.groupby("symbol")}

    t_min, t_max = prem["open_time"].min(), prem["open_time"].max()
    cutoff = t_min + 0.70 * (t_max - t_min)
    first_bar = prem.groupby("symbol", observed=True)["open_time"].min().to_dict()
    print(f"split 70/30 à {pd.Timestamp(cutoff, unit='ms').date()} | "
          f"syms premium {len(first_bar)}, klines 15m {len(kmap)}")

    parts = []
    for s, g in prem.groupby("symbol", observed=True, sort=False):
        if s not in kmap:
            continue
        k = kmap[s].reindex(g["open_time"].to_numpy())
        tr = build_trades(g["premium_open"].to_numpy(), g["premium_close"].to_numpy(),
                          g["open_time"].to_numpy(), k["open"].to_numpy(),
                          k["close"].to_numpy(), first_bar[s])
        if len(tr):
            tr["symbol"] = str(s)
            parts.append(tr)
    tr = pd.concat(parts, ignore_index=True)
    tr["month"] = pd.to_datetime(tr["ts"], unit="ms").dt.to_period("M").astype(str)
    print(f"\ntrades listing <{AGE_MAX_J}j : {len(tr):,} "
          f"(klines perp manquantes comptées comme non-évaluables)")

    print("\n== BLOC STATS (trades VALIDES, net 8 bps) ==")
    tr["period"] = np.where(tr["ts"] < cutoff, "TRAIN", "VAL")  # créé ici aussi (judge le recrée)
    for per in ("TRAIN", "VAL"):
        sub = tr[(tr["period"] == per) & tr["valid"]]
        if len(sub):
            m = sub.groupby("month")["pnl_bps"].sum()
            print(f"{per}: n={len(sub):,} WR={(sub['pnl_bps']>0).mean()*100:.1f}% "
                  f"esp={sub['pnl_bps'].mean():+.2f} bps | mois {(m>0).sum()}/{len(m)} pos | "
                  f"record {m.cumsum().max():+.0f} bps")

    checks, verdict = judge(tr, cutoff)
    print("\n== CRITÈRES PRÉ-ENREGISTRÉS ==")
    for name, ok, val in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:38s} {val}")
    print(f"\nVERDICT: {verdict}  (gate lab_ledger OBLIGATOIRE avant CE run ; log après)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
