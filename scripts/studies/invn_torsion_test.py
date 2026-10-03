# invn_torsion_test.py — L'ÉVALUATEUR de l'INV-N « Torsion du Premium » (verdict ~28/10).
# Pré-enregistrement : reports/aster/inv-n-torsion-premium-preenregistrement-2026-10.md (RIGIDE).
#
# FLUX OBLIGATOIRE :
#   1. ~28/10 (fenêtre premium_history ≥ 30 j) : lab_ledger check --family aster-institutions \
#        --strategy premium_torsion --hypothesis "INV-N torsion premium |Z|>=3 : reversion <2h + impact 4-12h"
#   2. si exit 0 → CE script (sans --dry-run) ; verdict → lab_ledger log. FAIL = gravé, STOP.
#   3. --dry-run = plomberie seule (fenêtre < 30 j), ne rend AUCUN verdict, ne consomme pas le budget.
#
# PIÈGE D'UNITÉ ÉVITÉ PAR CONSTRUCTION : le champ premium_pct du WS est en DÉCIMAL malgré son
# nom (mémoire 03/10) — l'évaluateur recalcule le premium depuis mark_price/index_price BRUTS.
# CONDITIONNEUR, jamais un signal autonome (le pré-enregistrement l'exige — le verdict qualifie
# le premium comme filtre de timing pour les autres flux).

import argparse
import sqlite3
import sys
import numpy as np
import pandas as pd

DB = "data/warehouse/klines.db"
Z_TH, Z_WIN = 3.0, "7D"
SMOOTH = "60s"
HALF_LIFE_MAX_H = 2.0
HORIZONS_H = [4, 12]
ETALON_BPS = 12.2     # l'étalon du pré-enregistrement (espérance nette à battre)
COST_BPS = 18.0       # garde-fou RT du pré-enregistrement
MIN_N = 20            # n minimal par côté et par période
WINDOW_MIN_D = 30     # la fenêtre minimale pour un VERDICT (forward-only)


def build_events(sym, df, first_ts, last_ts):
    """df : index datetime, colonnes prem (décimal), mark. Retourne events + timeline."""
    p = df["prem"].rolling(SMOOTH).mean().dropna()
    mu = p.rolling(Z_WIN, min_periods=int(0.5 * 86400 / 60)).mean()   # ≥ 3,5 j de données
    sd = p.rolling(Z_WIN, min_periods=int(0.5 * 86400 / 60)).std()
    z = (p - mu) / sd
    cand = z[np.abs(z) >= Z_TH].index
    events, last_resolve = [], None
    for t in cand:
        i = p.index.get_loc(t)
        if last_resolve is not None and t <= last_resolve:
            continue
        z0, p0, m0 = z[t], p[t], df["mark"].asof(t)
        # H1 : demi-vie = temps de retour à mi-chemin de la moyenne
        target = p0 - (p0 - mu[t]) / 2.0
        after = p.iloc[i:]
        crossed = after[after <= target] if z0 > 0 else after[after >= target]
        half_h = (crossed.index[0] - t).total_seconds() / 3600 if len(crossed) else np.nan
        last_resolve = t + pd.Timedelta(hours=max(half_h if half_h == half_h else 6, 2))
        ev = {"symbol": sym, "ts": t, "z": z0, "dir": -np.sign(z0), "half_h": half_h,
              "period": "TRAIN" if (t.timestamp() * 1000
                                    < first_ts + 0.5 * (last_ts - first_ts)) else "VAL"}
        for h in HORIZONS_H:
            m_h = df["mark"].asof(t + pd.Timedelta(hours=h))
            ev[f"ret{h}h_bps"] = (m_h / m0 - 1.0) * 1e4 if m0 > 0 else np.nan
        events.append(ev)
    return events


def judge(ev, window_d):
    """Les 2 hypothèses pré-enregistrées. Retourne (lignes, verdict, dry_run)."""
    dry = window_d < WINDOW_MIN_D
    tr = pd.DataFrame(ev)
    lines = []
    if len(tr) == 0:
        return ["aucun événement |Z|>=3"], ("DRY-RUN (plomberie OK, 0 event)" if dry else "FAIL"), dry
    for h in HORIZONS_H:
        tr[f"pnl{h}_bps"] = tr["dir"] * tr[f"ret{h}h_bps"] - COST_BPS
        tr[f"inv{h}_bps"] = -tr["dir"] * tr[f"ret{h}h_bps"] - COST_BPS

    # H1 : demi-vie < 2 h en calibration ET validation, n >= 20 total
    hl = tr["half_h"].dropna()
    h1_parts = []
    for per in ("TRAIN", "VAL"):
        s = hl[tr.loc[hl.index, "period"] == per] if len(hl) else pd.Series(dtype=float)
        med = s.median() if len(s) else np.nan
        h1_parts.append(f"{per}: médiane {med:.2f} h (n={len(s)})" if med == med else f"{per}: n=0")
    h1 = (hl.count() >= MIN_N
          and hl[tr["period"] == "TRAIN"].median() < HALF_LIFE_MAX_H
          and hl[tr["period"] == "VAL"].median() < HALF_LIFE_MAX_H)

    # H2 : espérance nette > étalon en TRAIN ET VAL, contrôle inverse battu, n >= 20/côté/période
    h2_parts, h2 = [], True
    for per in ("TRAIN", "VAL"):
        sub = tr[tr["period"] == per]
        for side in (1, -1):
            s = sub[sub["dir"] == side]
            if len(s) < MIN_N:
                h2 = False
                h2_parts.append(f"{per}/{'LONG' if side>0 else 'SHORT'}: n={len(s)}<20")
        if len(sub):
            e12 = sub["pnl12_bps"].mean()
            inv12 = sub["inv12_bps"].mean()
            ok = e12 > ETALON_BPS and e12 > inv12
            h2 = h2 and ok if len(sub) >= MIN_N else False
            h2_parts.append(f"{per}: 12h net {e12:+.1f} bps (inv {inv12:+.1f}, brut {e12 + COST_BPS:+.1f})")

    lines.append(f"H1 reversion : {h1_parts}")
    lines.append(f"H2 impact 4-12h : {h2_parts}")
    m = tr.groupby(tr["ts"].dt.to_period("M"))
    lines.append(f"events={len(tr)} | BLOC: " + ", ".join(
        f"{k} n={len(g)}" for k, g in m))
    verdict = ("DRY-RUN (pas un verdict — fenêtre " + f"{window_d:.0f} j < {WINDOW_MIN_D})"
               if dry else ("VALIDÉ (conditionneur)" if (h1 and h2) else "FAIL"))
    return lines, verdict, dry


def smoke():
    """Synthétique : un spike de premium sur index calme doit se révertir vite, sans drift prix."""
    idx_ts = pd.date_range("2026-09-01", periods=8 * 24 * 60, freq="60s")
    rng = np.random.default_rng(501)
    mark = 100 * np.exp(np.cumsum(rng.normal(0, 2e-5, len(idx_ts))))
    prem = rng.normal(0, 2e-4, len(idx_ts))
    spike = len(idx_ts) // 2
    prem[spike:spike + 60] = 0.01                      # +1 % pendant 1 h puis reversion
    df = pd.DataFrame({"prem": prem, "mark": mark}, index=idx_ts)
    ev = build_events("SMOKE", df, idx_ts[0].value // 10**6, idx_ts[-1].value // 10**6)
    assert len(ev) >= 1, "smoke: 0 event"
    e = ev[0]
    assert e["dir"] < 0 and e["half_h"] < 1.5, f"smoke: dir={e['dir']} half={e['half_h']}"
    lines, verdict, dry = judge(ev, window_d=8)
    print("SMOKE OK :", lines[0], "|", verdict)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="plomberie sur fenêtre réelle, aucun verdict")
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    if a.smoke:
        return smoke()

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    df = pd.read_sql_query(
        "SELECT symbol, mark_price, index_price, captured_at_ms FROM premium_history "
        "WHERE mark_price > 0 AND index_price > 0", con)
    con.close()
    df["ts"] = pd.to_datetime(df["captured_at_ms"], unit="ms")
    df["prem"] = df["mark_price"] / df["index_price"] - 1.0     # depuis les PRIX BRUTS (unité-immune)
    first_ts, last_ts = df["captured_at_ms"].min(), df["captured_at_ms"].max()
    window_d = (last_ts - first_ts) / 864e5
    print(f"fenêtre premium_history : {window_d:.1f} j, {len(df):,} lignes, "
          f"{df['symbol'].nunique()} symboles")

    events = []
    for sym, g in df.groupby("symbol"):
        g = (g.set_index("ts").sort_index()
             .rename(columns={"mark_price": "mark"})[["prem", "mark"]])
        if len(g) < 500:
            continue
        events += build_events(sym, g, first_ts, last_ts)

    print(f"\nevents |Z|>={Z_TH} : {len(events)}")
    lines, verdict, dry = judge(events, window_d)
    print("\n== CRITÈRES PRÉ-ENREGISTRÉS ==")
    for l in lines:
        print(" ", l)
    print(f"\nVERDICT: {verdict}")
    if dry and not a.dry_run:
        print("⚠️ fenêtre < 30 j : ceci n'est PAS un verdict — re-run après le 28/10 (gate d'abord).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
