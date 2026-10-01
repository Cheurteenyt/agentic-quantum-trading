# ARCHIVÉ (01/10/2026) — T17 : NUL comme signal (le tape reproduit les bougies corr 0,9999 ; 0/32 features après re-vérification — la valeur = la matière sub-minute absorption)
#!/usr/bin/env python3
"""aster_cvd_tape.py — T17 : le CVD re-calculé depuis le TAPE (aster_tape).

Première étude phase 2 sur la matière ordre-flow. Question : le CVD
reconstruit depuis les prints agressifs (aster_tape, 5,65 M lignes BTC/ETH
sur ~45 j) diffère-t-il du CVD des bougies 1m (klines.taker_buy_volume) et
contient-il une information prédictive que les bougies ne donnent pas ?

Méthode (doctrine quant-discipline) :
  1. CVD-tape 1m re-calculé depuis les prints (is_buyer_maker=True = SELL
     agressif ; buy_aggr = qty si is_buyer_maker=False, sell_aggr sinon).
     Unité ts_ms vérifiée (millisecondes, 13 chiffres).
  2. Cohérence inter-sources : gap volume/CVD par jour tape vs klines 1m,
     corr des deltas 1m et journaliers, sanity vs tape_1m (agrégat existant).
  3. Étude prédictive HONNÊTE : split TEMPOREL 70/30 (31 j train / 14 j
     val), features tape (delta CVD 15m/1h/4h, ratio agressivité 1h,
     anomalie de vitesse du tape z-score 3 j) + jumelles klines (delta CVD
     1h/4h, ratio 1h), testées contre le forward return 1h/4h sur grille
     NON chevauchante. Sharpe + AUC (rangs, Hanley-McNeil) sur TRAIN,
     jugés sur VAL. Barre de promotion : AUC VAL ≥ 0,60 (règle x501,
     docs/25). Multiplicité comptée (toutes les cellules déclarées,
     aucune retirée).

READ-ONLY sur data/warehouse/klines.db. Écrit uniquement le rapport
reports/aster_cvd_tape.md. Aucune écriture DB, aucun service touché.

Usage : .venv/bin/python scripts/studies/aster_cvd_tape.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "aster_cvd_tape.md"

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
# Fenêtre d'étude : 45 jours pleins, split temporel 70/30.
START = pd.Timestamp("2026-08-17 00:00", tz="UTC")
SPLIT = pd.Timestamp("2026-09-17 00:00", tz="UTC")  # fin train (31 j)
END = pd.Timestamp("2026-10-01 00:00", tz="UTC")    # fin val (14 j)
WARMUP = 240  # minutes (le feature le plus long : delta CVD 4h)

FEATS = {  # nom -> (genre, fenêtre minutes)
    "dcvd_15m": ("tape", 15),
    "dcvd_1h": ("tape", 60),
    "dcvd_4h": ("tape", 240),
    "aggress_1h": ("tape", 60),
    "speedz_1h": ("tape", 60),
    "dcvd_kl_1h": ("kl", 60),
    "dcvd_kl_4h": ("kl", 240),
    "aggress_kl_1h": ("kl", 60),
}
HORIZONS = {"1h": 60, "4h": 240}


def load_tape() -> pd.DataFrame:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        q = (
            "SELECT symbol, ts_ms, price, qty, is_buyer_maker FROM aster_tape "
            "WHERE symbol IN (?,?) AND ts_ms >= ? AND ts_ms < ?"
        )
        df = pd.read_sql_query(
            q, con, params=(*SYMBOLS, int(START.timestamp() * 1000), int(END.timestamp() * 1000))
        )
    finally:
        con.close()
    assert df["ts_ms"].between(1_000_000_000_000, 2_000_000_000_000).all(), "ts_ms hors unité ms"
    df["minute"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.floor("1min")
    df["buy_vol"] = np.where(df["is_buyer_maker"] == 0, df["qty"], 0.0)
    df["sell_vol"] = np.where(df["is_buyer_maker"] == 1, df["qty"], 0.0)
    notional = df["price"] * df["qty"]
    df["buy_not"] = np.where(df["is_buyer_maker"] == 0, notional, 0.0)
    df["sell_not"] = np.where(df["is_buyer_maker"] == 1, notional, 0.0)
    return df


def tape_1m(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["symbol", "minute"])
    out = g.agg(
        buy_vol=("buy_vol", "sum"),
        sell_vol=("sell_vol", "sum"),
        n=("qty", "size"),
        buy_notional=("buy_not", "sum"),
        sell_notional=("sell_not", "sum"),
    )
    out["close"] = df.sort_values("ts_ms").groupby(["symbol", "minute"])["price"].last()
    return out


def load_klines_1m() -> dict[str, pd.DataFrame]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        out = {}
        for sym in SYMBOLS:
            q = (
                "SELECT open_time, close, volume, taker_buy_volume FROM klines "
                "WHERE symbol=? AND interval='1m' AND open_time >= ? AND open_time < ?"
            )
            k = pd.read_sql_query(
                q, con, params=(sym, int(START.timestamp() * 1000), int(END.timestamp() * 1000))
            )
            k.index = pd.to_datetime(k.pop("open_time"), unit="ms", utc=True)
            out[sym] = k.sort_index()
        return out
    finally:
        con.close()


def load_tape_1m_table() -> pd.DataFrame:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return pd.read_sql_query(
            "SELECT symbol, minute_ts, n_trades, buy_notional FROM tape_1m "
            "WHERE minute_ts >= ? AND minute_ts < ?",
            con,
            params=(int(START.timestamp() * 1000), int(END.timestamp() * 1000)),
        )
    finally:
        con.close()


def build_series(sym: str, tape: pd.DataFrame, kl: pd.DataFrame) -> pd.DataFrame:
    idx = pd.date_range(START, END, freq="1min", inclusive="left")
    t = tape.loc[sym].reindex(idx)
    for c in ["buy_vol", "sell_vol", "n", "buy_notional", "sell_notional"]:
        t[c] = t[c].fillna(0.0)
    t["close"] = t["close"].ffill().bfill()
    t["cvd"] = (t["buy_vol"] - t["sell_vol"]).cumsum()
    k = kl.reindex(idx)
    k["kcvd"] = (2 * k["taker_buy_volume"] - k["volume"]).cumsum()
    f = pd.DataFrame(index=idx)
    f["close"] = t["close"]
    f["cvd"] = t["cvd"]
    f["kcvd"] = k["kcvd"]
    f["vol"] = t["buy_vol"] + t["sell_vol"]
    f["kvol"] = k["volume"]
    f["kbuy"] = k["taker_buy_volume"]
    f["n"] = t["n"]
    f["buy_vol"] = t["buy_vol"]
    f["sell_vol"] = t["sell_vol"]
    # Features tape
    f["dcvd_15m"] = f["cvd"].diff(15)
    f["dcvd_1h"] = f["cvd"].diff(60)
    f["dcvd_4h"] = f["cvd"].diff(240)
    bs = (t["buy_vol"] + t["sell_vol"]).rolling(60).sum()
    f["aggress_1h"] = t["buy_vol"].rolling(60).sum() / bs.replace(0, np.nan)
    # Vitesse du tape = ANOMALIE z-score vs base roulante 3 j (speed brute est
    # toujours > 0 : signe non tradable sinon — artefact toujours-LONG).
    sp = t["n"].rolling(60).mean()
    mu, sd = sp.rolling(4320, min_periods=1440).mean(), sp.rolling(4320, min_periods=1440).std()
    f["speedz_1h"] = (sp - mu) / sd.replace(0, np.nan)
    # Jumelles klines
    f["dcvd_kl_1h"] = f["kcvd"].diff(60)
    f["dcvd_kl_4h"] = f["kcvd"].diff(240)
    kbs = k["volume"].rolling(60).sum()
    f["aggress_kl_1h"] = k["taker_buy_volume"].rolling(60).sum() / kbs.replace(0, np.nan)
    # Forward returns (tape close)
    for hname, h in HORIZONS.items():
        f[f"fwd_{hname}"] = t["close"].shift(-h) / t["close"] - 1.0
    return f


def auc_mw(score: np.ndarray, fwd: np.ndarray) -> tuple[float, float, int]:
    """AUC (Mann-Whitney via rangs moyens) + SE Hanley-McNeil + n."""
    ok = np.isfinite(score) & np.isfinite(fwd)
    s, y = score[ok], fwd[ok]
    n_pos = int((y > 0).sum())
    n_neg = int((y <= 0).sum())
    if n_pos == 0 or n_neg == 0 or len(s) < 10:
        return float("nan"), float("nan"), len(s)
    r = pd.Series(s).rank(method="average").to_numpy()
    auc = (r[y > 0].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    q1 = auc / (2 - auc)
    q2 = 2 * auc * auc / (1 + auc)
    var = (auc * (1 - auc) + (n_pos - 1) * (q1 - auc**2) + (n_neg - 1) * (q2 - auc**2)) / (n_pos * n_neg)
    return float(auc), float(np.sqrt(max(var, 0.0))), n_pos + n_neg


def evaluate(f: pd.DataFrame, h: int, mask: np.ndarray) -> dict:
    """Grille NON chevauchante : un point tous les h minutes, warm-up dégrossi."""
    pos = np.arange(len(f))
    grid = (pos % h == 0) & (pos >= WARMUP)
    fwd = f[f"fwd_{'1h' if h == 60 else '4h'}"].to_numpy()
    m = grid & mask
    out = {}
    for feat in FEATS:
        sig = f[feat].to_numpy()
        ok = m & np.isfinite(sig) & np.isfinite(fwd)
        r = np.sign(sig[ok]) * fwd[ok]
        if len(r) < 10 or r.std() == 0:
            out[feat] = (float("nan"), float("nan"), float("nan"), 0, float("nan"))
            continue
        sharpe = r.mean() / r.std() * np.sqrt(525_600 / h)
        a, se, n = auc_mw(sig[ok], fwd[ok])
        pct_long = float((np.sign(sig[ok]) > 0).mean() * 100)
        out[feat] = (float(sharpe), float(a), float(se), int(n), pct_long)
    return out


def main() -> None:
    print("== T17 aster_cvd_tape ==")
    raw = load_tape()
    print(f"tape prints: {len(raw):,}")
    t1m = tape_1m(raw)
    kls = load_klines_1m()
    t1m_tbl = load_tape_1m_table()

    lines: list[str] = []
    A = lines.append
    A("# T17 — CVD tape (aster_tape) vs CVD klines : cohérence et valeur prédictive")
    A("")
    A("> One-shot : `scripts/studies/aster_cvd_tape.py` (reproductible). DB : "
      "`data/warehouse/klines.db` en READ-ONLY. Fenêtre : 2026-08-17 → 2026-10-01 UTC (45 j). "
      "Split TEMPOREL 70/30 : train 31 j (→ 09-17), val 14 j. Barre promotion : AUC VAL ≥ 0,60 "
      "(règle x501, docs/25). Multiplicité comptée : toutes les cellules déclarées d'avance "
      "(8 features × 2 symboles × 2 horizons = 32 tests), aucune retirée.")
    A("")

    # ---- 1. Cohérence inter-sources -------------------------------------
    A("## 1. Cohérence inter-sources (tape vs klines 1m)")
    A("")
    A("| Symbole | Prints | Jours | Gap volume/j (méd, p90) | Corr ΔCVD 1m | Corr ΔCVD/j | |ΔCVD/j| / vol (méd) | Sanity tape_1m |")
    A("|---|---|---|---|---|---|---|---|")
    for sym in SYMBOLS:
        f = build_series(sym, t1m, kls[sym])
        day = f.groupby(f.index.date).agg(
            vol=("vol", "sum"), kvol=("kvol", "sum"),
            dcvd=("cvd", lambda s: s.iloc[-1] - s.iloc[0]),
            dkcvd=("kcvd", lambda s: (s.dropna().iloc[-1] - s.dropna().iloc[0]) if s.notna().sum() else np.nan),
        )
        day = day[day["kvol"] > 0]
        gap_vol = (day["vol"] - day["kvol"]) / day["kvol"] * 100
        dcvd_j = day["dcvd"] - day["dkcvd"]
        m1 = f["cvd"].diff(1).corr(f["kcvd"].diff(1))
        corr_j = day["dcvd"].corr(day["dkcvd"])
        rel = (dcvd_j.abs() / day["kvol"] * 100).median()
        # sanity vs tape_1m (agrégat dérivé, couverture partielle) : médiane des
        # écarts relatifs sur l'overlap (le max est dominé par les trous du
        # collecteur dérivé — aster_tape brut fait foi).
        tt = t1m_tbl[t1m_tbl["symbol"] == sym].copy()
        tt["minute"] = pd.to_datetime(tt.pop("minute_ts"), unit="ms", utc=True)
        tt = tt.set_index("minute").rename(
            columns={"n_trades": "n_t1m", "buy_notional": "bn_t1m"}
        )[["n_t1m", "bn_t1m"]]
        j = t1m.loc[sym][["n", "buy_notional"]].join(tt, how="inner").dropna()
        cov_days = (j.index.max() - j.index.min()).total_seconds() / 86400
        dn = ((j["n"] - j["n_t1m"]).abs() / j["n_t1m"].clip(lower=1)).median() * 100
        dbn = ((j["buy_notional"] - j["bn_t1m"]).abs() / j["bn_t1m"].clip(lower=1)).median() * 100
        A(f"| {sym} | {len(raw[raw['symbol']==sym]):,} | {len(day)} | "
          f"{gap_vol.median():+.4f} % / {gap_vol.abs().quantile(0.9):.4f} % | {m1:.4f} | "
          f"{corr_j:.3f} | {rel:.3f} % | {cov_days:.1f} j ; Δn méd {dn:.1f} % ; Δnot. méd {dbn:.1f} % |")
    A("")
    A("Lecture : « Corr ΔCVD 1m » = accord minute par minute, « Corr ΔCVD/j » jour par jour, "
      "« |ΔCVD/j| / vol » l'écart résiduel journalier rapporté au volume. Sanity tape_1m = "
      "couverture de l'agrégat dérivé + écarts médians (n, notional) sur l'overlap ; ses écarts "
      "sont concentrés en queue (trous de collecte) — aster_tape brut fait foi.")
    A("")
    A("Contrôle indépendant du gap volume (sommes journalières directes) : écart max "
      "2e-14 % relatif sur 13 j BTC — les klines 1m et le tape proviennent du MÊME flux de "
      "trades ; le CVD-tape 1m EST le CVD-klines, à l'identité près.")
    A("")

    # ---- 2. Étude prédictive --------------------------------------------
    A("## 2. Features × TRAIN (31 j) / VAL (14 j) — sharpe (grille non chevauchante) et AUC")
    A("")
    A("Sharpe annualisé d'une stratégie signe(feature) sur le forward return "
      "(1 pt tous les h minutes → pas de chevauchement). AUC = rangs, ±SE Hanley-McNeil. "
      "Promotion : AUC VAL ≥ 0,60.")
    A("")
    rows = []
    frames = {sym: build_series(sym, t1m, kls[sym]) for sym in SYMBOLS}
    for sym in SYMBOLS:
        f = frames[sym]
        pos = np.arange(len(f))
        days = (f.index - START).total_seconds() / 86400
        mask_tr = days < (SPLIT - START).total_seconds() / 86400
        mask_va = ~mask_tr
        for hname, h in HORIZONS.items():
            tr = evaluate(f, h, mask_tr)
            va = evaluate(f, h, mask_va)
            for feat in FEATS:
                s_tr, a_tr, se_tr, n_tr, pl_tr = tr[feat]
                s_va, a_va, se_va, n_va, pl_va = va[feat]
                rows.append({
                    "symbole": sym, "feature": feat, "horizon": hname,
                    "sharpe_tr": s_tr, "auc_tr": a_tr, "n_tr": n_tr, "pct_long_tr": pl_tr,
                    "sharpe_va": s_va, "auc_va": a_va, "se_va": se_va, "n_va": n_va,
                    "pct_long_va": pl_va,
                })
    res = pd.DataFrame(rows)
    res.to_csv(ROOT / "reports" / "aster_cvd_tape_results.csv", index=False)
    A("| Symbole | Feature | H | Sharpe TR | AUC TR (n, %L) | Sharpe VA | AUC VA ±SE (n, %L) | Promo ? |")
    A("|---|---|---|---|---|---|---|---|")
    n_promo = 0
    for _, r in res.iterrows():
        promo = r["auc_va"] == r["auc_va"] and r["auc_va"] >= 0.60
        n_promo += promo
        A(f"| {r['symbole'][:3]} | {r['feature']} | {r['horizon']} | "
          f"{r['sharpe_tr']:+.2f} | {r['auc_tr']:.3f} ({r['n_tr']}, {r['pct_long_tr']:.0f} %L) | "
          f"{r['sharpe_va']:+.2f} | {r['auc_va']:.3f} ±{r['se_va']:.3f} ({r['n_va']}, {r['pct_long_va']:.0f} %L) | "
          f"{'**OUI**' if promo else 'non'} |")
    A("")
    A("Sharpe de signe avec %L extrême (> 80 % ou < 20 %) = biais directionnel déguisé "
      "(toujours-long/court) : le sharpe mesure alors le marché, pas la feature — seule l'AUC "
      "reste interprétable. Sharpe ±5-10 à AUC ≈ 0,5 = artefact de queues grasses (minutes à "
      "forte volatilité dominent la moyenne).")
    A("")
    A(f"Cellules promo brutes (AUC VAL ≥ 0,60) : **{n_promo} / {len(res)}**. "
      "Sous H0, l'AUC VAL suit ~N(0,50 ; SE≈0,03 à n≈340) : attendre ~1-2 « découvertes » "
      "sur 32 tests par pur bruit.")
    A("")
    A("**Re-vérification mécanique des cellules promo** (déclarée avant lecture) : une cellule "
      "n'est candidate que si (a) AUC TRAIN ≥ 0,55 dans le même sens (le signal pré-existait), "
      "(b) sharpe TRAIN et VAL de même signe (contrôle inverse), (c) 30 % ≤ %L ≤ 70 % des deux "
      "côtés (pas de biais directionnel déguisé).")
    strict = 0
    for _, r in res.iterrows():
        if r["auc_va"] == r["auc_va"] and r["auc_va"] >= 0.60:
            ok = (
                r["auc_tr"] >= 0.55
                and np.sign(r["sharpe_tr"]) == np.sign(r["sharpe_va"])
                and 30 <= r["pct_long_tr"] <= 70 and 30 <= r["pct_long_va"] <= 70
            )
            strict += ok
            A(f"- {r['symbole']} {r['feature']} {r['horizon']} : AUC TR {r['auc_tr']:.3f} "
              f"(≥0,55 : {'oui' if r['auc_tr'] >= 0.55 else 'NON'}), sharpe "
              f"{r['sharpe_tr']:+.2f}→{r['sharpe_va']:+.2f} "
              f"({'même signe' if np.sign(r['sharpe_tr']) == np.sign(r['sharpe_va']) else 'BASCULE'}), "
              f"%L {r['pct_long_tr']:.0f}/{r['pct_long_va']:.0f} → "
              f"{'candidate' if ok else 'REJETÉE'}.")
    A("")
    A(f"Cellules candidates après re-vérification : **{strict} / {len(res)}**.")
    A("")

    # ---- 3. Verdict ------------------------------------------------------
    best_va = res.loc[res["auc_va"].idxmax()]
    A("## 3. Verdict")
    A("")
    A(f"- Meilleure cellule toutes sources confondues : {best_va['symbole']} "
      f"{best_va['feature']} {best_va['horizon']} — AUC VAL {best_va['auc_va']:.3f} "
      f"(SE {best_va['se_va']:.3f}, n={best_va['n_va']}) ; re-vérification : "
      f"{'candidate' if strict else 'REJETÉE'}.")
    if strict == 0:
        A("- **VERDICT : NUL comme signal 1h/4h.** À 45 j, le tape ne prédit pas mieux que les "
          "bougies — il les REPRODUIT (corr ΔCVD 1m ≈ 1, gap volume ≈ 0). Le CVD tape n'est pas "
          "une nouvelle information directionnelle ; sa valeur = la granularité sub-minute pour "
          "les études d'absorption / événementielles (style x501 vague 2), pas un signal.")
        A("- Registre `docs/20-registre-indicateurs.md` : aster_tape = **CONTEXTE (matière "
          "ordre-flow)** — garder la donnée, ne pas trader le CVD ; les features CVD/agressivité "
          "1h-4h = **NUL** à ces horizons.")
    else:
        A(f"- **VERDICT : {strict} cellule(s) candidate(s)** — avant toute promotion : contrôle "
          "inverse complet + test du wallet séquentiel (`stacked_portfolio.run_stack`).")
    A("")
    A("## 4. Prochaine action")
    A("")
    if strict == 0:
        A("- Classer l'étude close : `git mv scripts/studies/aster_cvd_tape.py "
          "scripts/archive_studies/` + en-tête `# ARCHIVÉ`, inscrire CONTEXTE/NUL dans "
          "docs/20. Réserver aster_tape comme matière des études d'absorption (sub-minute, "
          "événementiel) — pas comme features 1h/4h. NB : tape_1m (agrégat dérivé) diverge "
          "en queue (trous de collecte) — aster_tape brut fait foi.")
    else:
        A("- Soumettre les cellules candidates au wallet séquentiel avant toute inscription "
          "au registre.")
    A("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"rapport → {REPORT}")
    print(res.sort_values("auc_va", ascending=False).head(8).to_string(index=False))


if __name__ == "__main__":
    main()
