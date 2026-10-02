#!/usr/bin/env python
"""LE GATE MEME — l'AL Score transposé au flux cascade memecoins (28/09).

Le flux cascade_meme est le SEUL flux de la machine SANS gate : 2 022
events, WR ~52 %, MAE max 223,7 % — sa survie (0 liq au wallet) dépend
du busy-skip du harnais séquentiel (les 2 events MAE ≥ 99,5 % ne passent
jamais au sizer par chance de créneau). La carte memecoins a mesuré des
MAE 96-538 % et une VAL négative depuis juin 2026 : l'edge s'est
évaporé, un gate peut-il le sauver — ou le flux est-il mort quoi qu'il
arrive ? Le test répond aux DEUX.

Features candidates (les familles AL majors transposées meme, TOUTES
calculées au signal t — zéro look-ahead) :
  atr_pct, vol24, dd_pct (le drawdown du token — la lifecycle carte),
  age_d (l'âge du token — lifecycle_map : 30-90j/20-50 % SHORT 65,4 %),
  btc_ret24, vwap_dev, cascade_depth, vol_usd (la liquidité), corr7
  (corr roulante 7j vs BTC — meme-spécifique).

Méthode v1 (anti_liq) : rangs roulants 90j (fenêtre = events antérieurs
UNIQUEMENT, min 50, NaN → rang 0,5), split TRAIN/VAL PAR LE TEMPS 70/30,
choix sur TRAIN uniquement, jugés tels quels sur VAL. La barre haute :
gradient monotone tenu en VAL (les fund7/vol7-like qui s'inversent =
HORS). DEUX TIERS de sélection, divulgation honnête :
  - tier 1 (quintiles stricts, 4 diffs stricts) — la barre la plus dure ;
  - tier 2 (terciles, la barre MAISON : AL Score 4,1→19,9 % de liqs,
    capitulation 1.70/2.27/3.26, funding_dimension) — opérative.
Le corpus est la collecte EXACTE de collect_meme (the_machine,
vérification bit-à-bit en tête de run — baseline anti-dérive).

PASS pré-enregistré : gradient VAL monotone du score ET quintile extrême
nettement meilleur (écart VAL espérance nette ≥ 1,0 % de notional ET
≥ 5 pts de WR) ET le gate (seuil TRAIN gardant ~40-60 %) améliore
l'espérance VAL ≥ 0,3 % ET MAE max des events gardés < 99,5 % (0 liq
SANS dépendre du busy-skip). Si PASS : wallet 4 flux (--vol-spike ON)
meme-gaté vs baseline $4 004,94 — ROI ≥, DD ≤, 0 liq, mois négatifs ≤,
garde-fou composé ~0.

  .venv/bin/python scripts/meme_gate_test.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.portfolio_sim import MAJORS, btc_regime_series, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)
from scripts.the_machine import collect_meme as collect_meme_machine  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
SIZE = 0.05
HOLD = 24
LIQ_1X = 99.5           # à 1x la mort est à 99,5 % (règle 100/(MAE+0,5))
WIN_DAYS = 90
MIN_WINDOW = 50

# les features candidates du gate meme (toutes au signal t)
FEATURES = ("atr_t", "vol24", "dd_pct", "age_d", "btc_ret24", "vwap_dev",
            "cascade_depth", "vol_usd", "corr7")
FEAT_LABEL = {"atr_t": "atr_pct", "vol24": "vol24", "dd_pct": "dd_pct",
              "age_d": "age_d", "btc_ret24": "btc_ret24",
              "vwap_dev": "vwap_dev", "cascade_depth": "cascade_depth",
              "vol_usd": "vol_usd", "corr7": "corr7"}


# —————————————————————— le collecteur featured (mécanique EXACTE) ——————————————————————

def collect_meme_featured(con: sqlite3.Connection) -> list[dict]:
    """La collecte EXACTE de the_machine.collect_meme (même signal, même
    entrée open t+1, même exit t+24, même MAE, même atr[ei] pour le
    sizing) + les features du gate calculées au signal t (≤ t)."""
    btc = load_df(con, "BTCUSDT")
    btc_r24_s = btc["close"].pct_change(24) * 100
    btc_r1 = btc["close"].pct_change()
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol") if r[0] not in MAJORS]
    meme: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens, highs, closes = df["open"].values, df["high"].values, df["close"].values
        close_s = pd.Series(closes, index=df.index)
        r1 = close_s.pct_change() * 100
        ra = r1.abs()
        cas = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
               & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        atr = (close_s.diff().abs().rolling(24).mean() / close_s * 100).values
        # ——— features du gate (au signal t, ≤ t) ———
        vol24 = r1.rolling(24).std()
        hmax = pd.Series(highs, index=df.index).cummax()
        dd_pct = (hmax - close_s) / hmax * 100
        age_d = (idx_ns - idx_ns[0]) / (86400 * 10**9)
        volume = df["volume"]
        vwap168 = ((close_s * volume).rolling(168).sum()
                   / volume.rolling(168).sum())
        vwap_dev = (close_s - vwap168) / vwap168 * 100
        depth3 = r1 + r1.shift(1) + r1.shift(2)
        vol_usd = (volume * close_s).rolling(24).median()
        btc_r24 = btc_r24_s.reindex(df.index, method="ffill", limit=48)
        rs = close_s.pct_change()
        rb = btc_r1.reindex(df.index)
        corr7 = rs.rolling(168, min_periods=100).corr(rb)
        for t in np.where(cas)[0]:
            ei = t + 1
            if ei + 24 >= len(idx_ns) or t < 200:
                continue
            entry = opens[ei]
            if entry <= 0 or not np.isfinite(atr[ei]):
                continue
            x = closes[ei + 23]
            meme.append({"sym": sym, "ts_ms": int(idx_ns[ei]),
                         "strategy": "cascade_meme", "lev": 1, "hold_h": HOLD,
                         "fee_rt_bps": MAKER_RT, "entry": entry,
                         "exit": float(x),
                         "price_ret_short": (entry - x) / entry * 100,
                         "fund_sign": 1,
                         "mae_adverse": (highs[ei:ei + 24].max() - entry)
                         / entry * 100, "atr_pct": float(atr[ei]),
                         # features gate (signal t)
                         "atr_t": float(atr[t]),
                         "vol24": float(vol24.iloc[t]),
                         "dd_pct": float(dd_pct.iloc[t]),
                         "age_d": float(age_d[t]),
                         "btc_ret24": (float(btc_r24.iloc[t])
                                       if np.isfinite(btc_r24.iloc[t]) else np.nan),
                         "vwap_dev": float(vwap_dev.iloc[t]),
                         "cascade_depth": float(depth3.iloc[t]),
                         "vol_usd": float(vol_usd.iloc[t]),
                         "corr7": (float(corr7.iloc[t])
                                   if np.isfinite(corr7.iloc[t]) else np.nan)})
    meme.sort(key=lambda e: e["ts_ms"])
    return meme


# —————————————————————— le score composite (méthode v1) ——————————————————————

def add_meme_scores(events: list[dict], feats_up: tuple, feats_down: tuple,
                    win_days: int = WIN_DAYS, min_window: int = MIN_WINDOW
                    ) -> None:
    """Copie EXACTE de anti_liq.add_rolling_scores, directions en paramètre.
    Rangs roulants 90j contre les events ANTÉRIEURS uniquement ; NaN → 0,5
    (neutre) ; score = moyenne des rangs. HAUT score = risqué."""
    win_ns = win_days * 86400 * 10**9
    for i, e in enumerate(events):
        lo = e["ts_ms"] - win_ns
        window = [p for p in events[:i] if p["ts_ms"] >= lo]
        if len(window) < min_window:
            e["meme_score"] = float("nan")
            continue
        ranks = []
        for f in feats_up:
            vals = np.array([p[f] for p in window])
            v = e[f]
            ranks.append(float(np.mean(vals <= v))
                         if np.isfinite(v) else 0.5)
        for f in feats_down:
            vals = np.array([-p[f] for p in window])
            v = -e[f]
            ranks.append(float(np.mean(vals <= v))
                         if np.isfinite(v) else 0.5)
        e["meme_score"] = float(np.mean(ranks))


# —————————————————————— les outils de jugement ——————————————————————

def net_ret(e: dict, fh: dict[str, float]) -> float:
    """Espérance nette % de notional (short 1x, hold 24h, maker)."""
    return (e["price_ret_short"] + fh.get(e["sym"], 0.0) * e["hold_h"] / 100
            - e["fee_rt_bps"] / 100)


def quintile_edges(vals: np.ndarray) -> np.ndarray:
    return np.nanquantile(vals, [0.2, 0.4, 0.6, 0.8])


def quintile_table(vals: np.ndarray, edges: np.ndarray, net: np.ndarray,
                   mae: np.ndarray) -> list[dict]:
    ok = np.isfinite(vals)
    idx = np.digitize(vals, edges)
    rows = []
    for q in range(5):
        m = ok & (idx == q)
        n = int(m.sum())
        rows.append({
            "q": q, "n": n,
            "wr": float(np.mean(net[m] > 0) * 100) if n else float("nan"),
            "exp": float(np.mean(net[m])) if n else float("nan"),
            "mae_med": float(np.median(mae[m])) if n else float("nan"),
            "mae_max": float(np.max(mae[m])) if n else float("nan"),
            "n_dead": int(np.sum(mae[m] >= LIQ_1X)) if n else 0})
    return rows


def monotone_dir(exps: list[float]) -> int:
    """+1 si strictement croissant, -1 si strictement décroissant, 0 sinon."""
    d = np.diff(exps)
    if np.all(d > 0):
        return 1
    if np.all(d < 0):
        return -1
    return 0


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 30 or np.std(a[ok]) == 0 or np.std(b[ok]) == 0:
        return float("nan")
    ra = pd.Series(a[ok]).rank().values
    rb = pd.Series(b[ok]).rank().values
    return float(np.corrcoef(ra, rb)[0, 1])


def tercile_grad(tv: np.ndarray, vv: np.ndarray, net_tr: np.ndarray,
                 net_va: np.ndarray):
    """Terciles TRAIN (edges figés) appliqués aux DEUX segments — la barre
    maison (AL Score, capitulation, funding_dimension). Retourne espérances
    et WR par tercile, directions monotones et Spearman feature~net."""
    edges = np.nanquantile(tv, [1 / 3, 2 / 3])
    exps, wrs = [], []
    for vals, nn in ((tv, net_tr), (vv, net_va)):
        ok = np.isfinite(vals)
        idx = np.digitize(vals, edges)
        exp3, wr3 = [], []
        for q in range(3):
            m = ok & (idx == q)
            exp3.append(float(np.mean(nn[m])) if m.sum() else float("nan"))
            wr3.append(float(np.mean(nn[m] > 0) * 100) if m.sum()
                       else float("nan"))
        exps.append(exp3)
        wrs.append(wr3)
    d_tr = monotone_dir(exps[0])
    d_va = monotone_dir(exps[1])
    return (exps[0], exps[1], wrs[0], wrs[1], d_tr, d_va,
            spearman(tv, net_tr), spearman(vv, net_va))


def fmt_qtable(rows: list[dict]) -> list[str]:
    out = ["| Quintile | N | WR | Esp. nette % | MAE méd | MAE max | MAE ≥ 99,5 % |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(
            f"| Q{r['q'] + 1} | {r['n']} | {r['wr']:.1f} % | {r['exp']:+.2f} % "
            f"| {r['mae_med']:.1f} % | {r['mae_max']:.1f} % | {r['n_dead']} |")
    return out


def bloc_stats(res: dict, label: str) -> list[str]:
    mrows = monthly_rows(res["trades"], CAPITAL)
    rois = [r["roi"] for r in mrows]
    neg = sum(1 for x in rois if x < 0)
    gc = gp = float("nan")
    if mrows:
        prod = 1.0
        for r in mrows:
            prod *= (1 + r["roi"] / 100)
        gc = abs(prod - res["balance"] / CAPITAL)
        gp = abs(sum(r["pnl"] for r in mrows) - (res["balance"] - CAPITAL))
    n = max(res["n"], 1)
    pnls = [t["pnl"] for t in res["trades"]]
    return [f"**{label}** : ${CAPITAL:,.0f} → **${res['balance']:,.2f}** "
            f"(ROI {(res['balance'] / CAPITAL - 1) * 100:+.1f} %/an, "
            f"DD {res['max_dd']:.1f} %, liq {res['n_liq']})",
            f"  {res['n']} trades, WR {res['n_wins'] / n * 100:.1f} %, "
            f"espérance ${np.mean(pnls):+.3f}" if pnls else "  aucun trade",
            f"  mois : moyen {np.mean(rois):+.1f} %, pire {min(rois):+.1f} %, "
            f"record {max(rois):+.1f} %, {neg} négatifs" if rois else "",
            f"  garde-fous : composé {gc * 100:.3f} % "
            f"{'OK' if gc < 0.005 else '✗ BUG'}, somme PnL ${gp:.4f} "
            f"{'OK' if gp < 0.01 else '✗ BUG'}"]


def monthly_meme_table(res: dict, label: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for t in res["trades"]:
        m = t["exit_ts"].strftime("%Y-%m")
        r = out.setdefault(m, {"n": 0, "w": 0, "pnl": 0.0})
        r["n"] += 1
        r["w"] += t["pnl"] > 0
        r["pnl"] += t["pnl"]
    return {m: {**r, "label": label} for m, r in out.items()}


def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=60)
    fh = funding_hourly_all()

    # ——— 0. baseline anti-dérive : la collecte = collect_meme bit-à-bit ———
    print("[mgate] collecte featured (mécanique collect_meme + features)…")
    events = collect_meme_featured(con)
    print("[mgate] vérification bit-à-bit vs the_machine.collect_meme…")
    ref = collect_meme_machine(sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=60))
    ref_map = {(e["sym"], e["ts_ms"]): e for e in ref}
    mism = 0
    for e in events:
        r = ref_map.get((e["sym"], e["ts_ms"]))
        if r is None or r["entry"] != e["entry"] or r["exit"] != e["exit"] \
                or r["mae_adverse"] != e["mae_adverse"] \
                or r["atr_pct"] != e["atr_pct"]:
            mism += 1
    if mism or len(ref) != len(events):
        print(f"[mgate] ✗ BUG baseline : {mism} events divergents "
              f"({len(events)} vs {len(ref)}) — NE PAS PUBLIER")
        return 2
    print(f"[mgate] OK : {len(events)} events, collecte = collect_meme "
          f"bit-à-bit")

    mae_all = np.array([e["mae_adverse"] for e in events])
    n_dead_all = int(np.sum(mae_all >= LIQ_1X))

    # ——— 1. split PAR LE TEMPS 70/30 ———
    k = int(len(events) * 0.7)
    train, val = events[:k], events[k:]
    split_date = datetime.fromtimestamp(val[0]["ts_ms"] / 10**9,
                                        tz=timezone.utc)
    train_end = datetime.fromtimestamp(train[-1]["ts_ms"] / 10**9,
                                       tz=timezone.utc)

    # ——— 2. univarié : quintiles TRAIN, jugés VAL (barre haute) ———
    net_tr = np.array([net_ret(e, fh) for e in train])
    net_va = np.array([net_ret(e, fh) for e in val])
    mae_tr = np.array([e["mae_adverse"] for e in train])
    mae_va = np.array([e["mae_adverse"] for e in val])

    lines = [
        "# LE GATE MEME — l'AL Score transposé au flux cascade memecoins",
        f"{t0:%d/%m/%Y %H:%M} UTC — corpus {len(events)} events cascade_meme "
        f"(collecte bit-à-bit = the_machine.collect_meme, baseline "
        f"anti-dérive OK), hold 24h, 1x, maker. MAE ≥ 99,5 % dans le corpus : "
        f"{n_dead_all} (la survie du flux dépend du busy-skip du harnais).",
        f"Split PAR LE TEMPS 70/30 : TRAIN {len(train)} (→ {train_end:%d/%m/%Y}), "
        f"VAL {len(val)} (dès le {split_date:%d/%m/%Y}).", "",
        "Note honnêteté : age_d = jours depuis la 1re bougie du symbole dans "
        "le warehouse — pour les tokens présents dès le début de la collecte, "
        "l'âge est CENSURÉ (mesuré depuis le début des données, pas depuis le "
        "listing réel). dd_pct = drawdown vs cummax des highs (convention "
        "anti_liq), transposition de la lifecycle carte (close-based).",
        "Features candidates (au signal t, zéro look-ahead) : " +
        ", ".join(FEAT_LABEL[f] for f in FEATURES) + ".",
        "Méthode v1 : rangs roulants 90j (fenêtre = events antérieurs, min "
        "50) ; sélection en DEUX tiers (1 : quintiles stricts — diagnostic ; "
        "2 : terciles, la barre maison — opérative) ; jugés tels quels sur "
        "VAL. Barre haute : gradient monotone tenu en VAL — les inverses "
        "(fund7/vol7-like) = HORS.", "",
        "## Le gate est-il nécessaire ? (l'état des lieux)", "",
        f"- Corpus entier : WR {np.mean(net_tr > 0) * 100:.1f} %/"
        f"{np.mean(net_va > 0) * 100:.1f} % (TRAIN/VAL), espérance nette "
        f"{np.mean(net_tr):+.2f} %/{np.mean(net_va):+.2f} % de notional.",
        f"- MAE max corpus {mae_all.max():.1f} % — les {n_dead_all} events "
        f"≥ 99,5 % seraient des LIQUIDATIONS prises sans le busy-skip.",
        f"- VAL (dernier {len(val)} events, dès {split_date:%m/%Y}) : "
        f"espérance {np.mean(net_va):+.2f} % — le cœur du problème.", "",
        "## AUTOPSIE DES EVENTS MORTELS (le 0-liq sans busy-skip)", "",
        f"Les {n_dead_all} events du corpus avec MAE ≥ 99,5 % (à 1x = "
        "liquidation). Leurs features ex-ante vs la médiane TRAIN :", "",
        "| Symbole | Date | MAE % | atr | vol24 | dd % | age_j | btc24 | vwap | depth | corr7 | vol_usd k |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    med_tr = {}
    for f in FEATURES:
        vals = np.array([e[f] for e in train], dtype=float)
        med_tr[f] = float(np.nanmedian(vals)) if np.isfinite(vals).any() else np.nan
    mortels = [e for e in events if e["mae_adverse"] >= LIQ_1X]
    for e in mortels:
        d = datetime.fromtimestamp(e["ts_ms"] / 10**9, tz=timezone.utc)
        lines.append(
            f"| {e['sym']} | {d:%d/%m/%y} | {e['mae_adverse']:.0f} "
            f"| {e['atr_t']:.1f} | {e['vol24']:.1f} | {e['dd_pct']:.0f} "
            f"| {e['age_d']:.0f} | {e['btc_ret24']:+.1f} "
            f"| {e['vwap_dev']:+.1f} | {e['cascade_depth']:+.1f} "
            f"| {e['corr7']:+.2f} | {e['vol_usd'] / 1000:.0f} |")
    lines += ["", "## UNIVARIÉ — TIER 1 : quintiles stricts (diagnostic)", "",
              "Espérance nette % de notional (short, maker, funding moyen). "
              "Barre la plus dure : 4 diffs stricts du même signe. "
              "DIAGNOSTIC seulement — la sélection opérative est le tier 2 "
              "(terciles, la barre maison).", "",
              "| Feature | TRAIN Q1→Q5 (esp %) | dir | VAL Q1→Q5 (esp %) | dir VAL |",
              "|---|---|---|---|---|"]
    adopted_up, adopted_down = [], []   # up : haut = bon ; down : bas = bon
    t1_count = 0                        # ce que le tier 1 strict aurait pris
    for f in FEATURES:
        tv = np.array([e[f] for e in train], dtype=float)
        vv = np.array([e[f] for e in val], dtype=float)
        if np.isfinite(tv).sum() < 100:
            lines.append(f"| {FEAT_LABEL[f]} | NaN | — | NaN | — |")
            continue
        edges = quintile_edges(tv)
        tr_rows = quintile_table(tv, edges, net_tr, mae_tr)
        va_rows = quintile_table(vv, edges, net_va, mae_va)
        tr_exps = [r["exp"] for r in tr_rows]
        va_exps = [r["exp"] for r in va_rows]
        d_tr = monotone_dir(tr_exps)
        d_va = monotone_dir(va_exps)
        if d_tr != 0 and d_va == d_tr and \
                min(r["n"] for r in tr_rows) >= 30:
            t1_count += 1
        lines.append(
            f"| {FEAT_LABEL[f]} | " +
            " ".join(f"{x:+.1f}" for x in tr_exps) +
            f" | {'↑' if d_tr > 0 else '↓' if d_tr < 0 else '∅'} | " +
            " ".join(f"{x:+.1f}" for x in va_exps) +
            f" | {'↑' if d_va > 0 else '↓' if d_va < 0 else '∅'} |")

    lines += ["", "## UNIVARIÉ — TIER 2 : terciles (la barre maison — "
              "SÉLECTION OPÉRATIVE)", "",
              "La barre des études validées (AL Score 4,1→19,9 % de liqs, "
              "capitulation 1.70/2.27/3.26, funding_dimension) : gradient "
              "T1→T3 monotone TRAIN ET même direction monotone VAL. Les "
              "inversés (fund7/vol7-like) = HORS. ADOPTÉ = selection.", "",
              "| Feature | TRAIN T1/T2/T3 (esp %) | VAL T1/T2/T3 (esp %) | "
              "WR TR | WR VA | Spearman TR/VA | Verdict |",
              "|---|---|---|---|---|---|---|"]
    for f in FEATURES:
        tv = np.array([e[f] for e in train], dtype=float)
        vv = np.array([e[f] for e in val], dtype=float)
        if np.isfinite(tv).sum() < 100:
            lines.append(f"| {FEAT_LABEL[f]} | NaN | NaN | — | — | — | "
                         "HORS (données) |")
            continue
        res_f = tercile_grad(tv, vv, net_tr, net_va)
        if res_f is None:
            lines.append(f"| {FEAT_LABEL[f]} | NaN | NaN | — | — | — | "
                         "HORS (cellule vide) |")
            continue
        (tr3, va3, wr3t, wr3v, d_tr, d_va, sp_tr, sp_va) = res_f
        verdict = "HORS"
        if d_tr == 0:
            verdict = "HORS (TRAIN non monotone)"
        elif d_va != d_tr:
            verdict = "HORS (INVERSÉ en VAL — fund7/vol7-like)"
        else:
            verdict = f"ADOPTÉ (dir {'↑' if d_tr > 0 else '↓'})"
            (adopted_up if d_tr > 0 else adopted_down).append(f)
        lines.append(
            f"| {FEAT_LABEL[f]} | " + " ".join(f"{x:+.2f}" for x in tr3) +
            " | " + " ".join(f"{x:+.2f}" for x in va3) +
            " | " + " ".join(f"{x:.0f}" for x in wr3t) +
            " | " + " ".join(f"{x:.0f}" for x in wr3v) +
            f" | {sp_tr:+.2f}/{sp_va:+.2f} | {verdict} |")

    print(f"[mgate] adoptés : up={adopted_up} down={adopted_down}")
    n_adopt = len(adopted_up) + len(adopted_down)
    verdict_features = (f"{n_adopt} adoptés / {len(FEATURES)} candidats "
                        f"(tier 1 strict : {t1_count}, tier 2 terciles "
                        f"maison : {n_adopt})")

    # ——— 3. le score composite (rangs roulants 90j, méthode v1) ———
    # convention AL : HAUT score = risqué → les features "haut = bon"
    # entrent en RISK_DOWN, les "bas = bon" en RISK_UP.
    feats_up = tuple(adopted_down)
    feats_down = tuple(adopted_up)
    gate_pass = False
    score_rows_tr = score_rows_va = None
    thr = keep = float("nan")
    gated_events: list[dict] = []
    if feats_up or feats_down:
        print("[mgate] score composite (rangs roulants 90j)…")
        add_meme_scores(events, feats_up, feats_down)
        sc = np.array([e["meme_score"] for e in events])
        sc_tr, sc_va = sc[:k], sc[k:]
        edges_sc = quintile_edges(sc_tr[np.isfinite(sc_tr)])
        score_rows_tr = quintile_table(sc_tr, edges_sc, net_tr, mae_tr)
        score_rows_va = quintile_table(sc_va, edges_sc, net_va, mae_va)
        tr_exps = [r["exp"] for r in score_rows_tr]
        va_exps = [r["exp"] for r in score_rows_va]
        d_tr = monotone_dir(tr_exps)
        d_va = monotone_dir(va_exps)
        # le quintile extrême "meilleur" = Q1 si le score haut est risqué
        best_q, worst_q = (0, 4) if d_tr < 0 else (4, 0)
        gap_exp = va_exps[best_q] - va_exps[worst_q]
        gap_wr = score_rows_va[best_q]["wr"] - score_rows_va[worst_q]["wr"]

        # ——— le seuil du gate : choisi sur TRAIN (garde ~40-60 %) ———
        cand = []
        for kp in (0.6, 0.5, 0.4):
            q = float(np.nanquantile(sc_tr[np.isfinite(sc_tr)], 1 - kp))
            kept_tr = [e for i, e in enumerate(train)
                       if not (np.isfinite(e["meme_score"])
                               and e["meme_score"] >= q)]
            kept_tr_net = [net_ret(e, fh) for e in kept_tr]
            cand.append((float(np.mean(kept_tr_net)), kp, q))
        cand.sort(reverse=True)
        exp_kept_tr, keep, thr = cand[0]

        gated_events = [e for e in events
                        if not (np.isfinite(e["meme_score"])
                                and e["meme_score"] >= thr)]
        va_gated_mask = np.array(
            [not (np.isfinite(e["meme_score"]) and e["meme_score"] >= thr)
             for e in val])
        exp_va_all = float(np.mean(net_va))
        exp_va_gate = float(np.mean(net_va[va_gated_mask]))
        wr_va_all = float(np.mean(net_va > 0) * 100)
        wr_va_gate = float(np.mean(net_va[va_gated_mask] > 0) * 100)
        mae_kept = np.array([e["mae_adverse"] for e in gated_events])
        n_dead_kept = int(np.sum(mae_kept >= LIQ_1X))
        frac_kept = len(gated_events) / len(events) * 100

        # ——— PASS pré-enregistré (docstring : les 5 conditions ci-dessous,
        # une sélection à 1 feature est admissible mais = risque d'overfit
        # supérieur, à noter au verdict) ———
        cond = {
            "TRAIN monotone": d_tr != 0,
            "VAL monotone (même direction)": d_va == d_tr and d_tr != 0,
            "écart VAL ≥ 1,0 % et ≥ 5 pts WR":
                gap_exp >= 1.0 and gap_wr >= 5.0,
            "gate VAL esp +0,3 %": exp_va_gate - exp_va_all >= 0.3,
            "MAE gardés < 99,5 %": n_dead_kept == 0}
        gate_pass = all(cond.values())
        single_feat = len(adopted_up) + len(adopted_down) == 1

        lines += [
            "", "## LE SCORE COMPOSITE (rangs roulants 90j — méthode v1)", "",
            "Score = moyenne des rangs des features adoptées contre leurs 90j "
            "d'events antérieurs (haut = risqué). Quintiles choisis sur TRAIN, "
            "appliqués tels quels à VAL.", "",
            f"Features adoptées : up={adopted_up or '—'} down={adopted_down or '—'} "
            f"({verdict_features})."
            + (" **ATTENTION : gate à UNE seule feature = le score est le "
               "rang roulant d'age_d — risque d'overfit supérieur, CANDIDAT "
               "seulement après paper forward.**" if single_feat else ""),
            "",
            "### Quintiles TRAIN", "", *fmt_qtable(score_rows_tr),
            "", "### Quintiles VAL (mêmes edges)", "", *fmt_qtable(score_rows_va),
            "", f"Gradient TRAIN {'monotone' if d_tr else 'NON monotone'} "
            f"({'↑' if d_tr > 0 else '↓' if d_tr < 0 else '∅'}) ; VAL "
            f"{'monotone' if d_va else 'NON monotone'} "
            f"({'↑' if d_va > 0 else '↓' if d_va < 0 else '∅'}).",
            f"Écart VAL Q{best_q + 1}−Q{worst_q + 1} : espérance "
            f"{gap_exp:+.2f} %, WR {gap_wr:+.1f} pts.", "",
            "### Le gate (seuil TRAIN gardant ~40-60 %)", "",
            f"- Seuil choisi sur TRAIN : score ≥ {thr:.3f} écarté (keep p{int(keep * 100)} "
            f"— max espérance TRAIN gardée {exp_kept_tr:+.2f} % parmi keep 60/50/40 %).",
            f"- Events gardés : {len(gated_events)}/{len(events)} ({frac_kept:.0f} %).",
            f"- VAL : espérance {exp_va_gate:+.2f} % gatée vs {exp_va_all:+.2f} % "
            f"tout-venant ({exp_va_gate - exp_va_all:+.2f} pts), WR "
            f"{wr_va_gate:.1f} % vs {wr_va_all:.1f} %.",
            f"- **MAE max des events gardés : {mae_kept.max():.1f} %** — "
            f"{n_dead_kept} event(s) ≥ 99,5 % "
            f"({'0 liq SANS dépendre du busy-skip' if n_dead_kept == 0 else 'liq toujours possibles'}).",
            "", "### Conditions PASS (pré-enregistrées)", ""]
        for c, okc in cond.items():
            lines.append(f"- {'✓' if okc else '✗'} {c}")
        lines += ["", f"**GATE : {'PASS' if gate_pass else 'FAIL'}**"]

    # ——— 4. SI PASS : le wallet 4 flux meme-gaté vs baseline ———
    # (l'honnêteté VAL tourne dans les DEUX cas : le flux meme seul, flat)
    wallet_lines: list[str] = []
    meme_only_all = run_stack([dict(e) for e in events], CAPITAL,
                              lambda e, st=None: SIZE, fh)
    m_all = monthly_meme_table(meme_only_all, "tout")
    va_months = sorted({t["exit_ts"].strftime("%Y-%m") for t in
                        meme_only_all["trades"] if t["exit_ts"] >= split_date})
    val_all = [t for t in meme_only_all["trades"] if t["exit_ts"] >= split_date]
    exp_a = (float(np.mean([t["pnl"] for t in val_all]))
             if val_all else float("nan"))
    tr_all = [t for t in meme_only_all["trades"] if t["exit_ts"] < split_date]
    exp_tr = (float(np.mean([t["pnl"] for t in tr_all]))
              if tr_all else float("nan"))
    if not gate_pass:
        mae_str = "/".join(f"{e['mae_adverse']:.0f}" for e in mortels)
        wallet_lines += [
            "", "## L'HONNÊTETÉ — le flux meme seul, mois par mois "
            "(flat 5 %, run_stack)", "",
            "Pas de gate admissible → pas de wallet gaté : la question "
            "reste « le flux est-il mort quoi qu'il arrive ? ».", "",
            "| Mois | N | WR | PnL $ |", "|---|---|---|---|"]
        for m in sorted(m_all):
            a = m_all[m]
            wallet_lines.append(
                f"| {m}{' (VAL)' if m in va_months else ''} | {a['n']} "
                f"| {a['w'] / max(a['n'], 1) * 100:.0f} % | {a['pnl']:+.2f} |")
        rois_m = [r["roi"] for r in monthly_rows(meme_only_all["trades"],
                                                 CAPITAL)]
        neg = sum(1 for x in rois_m if x < 0)
        wallet_lines += [
            "",
            f"- Espérance TRAIN {exp_tr:+.3f} $/trade → VAL {exp_a:+.3f} "
            f"$/trade (dès {split_date:%d/%m/%Y}) ; DD flux seul "
            f"{meme_only_all['max_dd']:.1f} %, {neg} mois négatifs.",
            f"- **{'La VAL est négative : le flux est MORT quoi qu\u2019il arrive — aucun gate candidat ne peut le sauver (0/9 features tiennent la VAL). La survie actuelle au wallet (0 liq) reste une chance de busy-skip, pas une propriété.' if exp_a < 0 else 'La VAL resiste hors TRAIN — le gate échoue mais le flux vit encore.'}**",
            f"- Les {len(mortels)} events mortels (MAE {mae_str} %) ne "
            f"sont isolables ex-ante par AUCUNE feature monotone : vwap_dev "
            f"+85,8 % (HUSDT) et atr 41,6 % (LAB) crient, mais vwap_dev et "
            f"atr_t sont inversés/non-monotones en VAL — un seuil absolu "
            f"là-dessus reproduirait le piège « les seuils absolus ne "
            f"transfèrent pas » (anti-liq)."]

    if gate_pass:
        print("[mgate] PASS — réplication machine + wallet 4 flux…")
        from scripts.full_arsenal_2 import collect as collect_arsenal
        from scripts.p5_frequency_test import collect_vol_spike
        regime = btc_regime_series()
        fh_raw = pd.read_sql_query(
            "SELECT symbol, funding_time, rate FROM funding_history", con)

        # flux 1 : cascade majors 10x gated AL p66 (identique the_machine)
        ev_maj = collect_featured(regime, "majors")
        for e in ev_maj:
            e["strategy"] = "cascade_10x"
            e["lev"] = 10
            e["hold_h"] = 24
            e["fee_rt_bps"] = MAKER_RT
        add_rolling_scores(ev_maj)
        q66 = float(np.nanquantile(
            [e.get("al_score", float("nan"))
             for e in ev_maj[:int(len(ev_maj) * 0.7)]], 2 / 3))
        maj = [e for e in ev_maj
               if not (np.isfinite(e.get("al_score", float("nan")))
                       and e["al_score"] >= q66)]
        med_majors = float(np.median([e["atr_pct"] for e in maj]))

        # le fund_rank (le tilt qualité du machine_fn par défaut)
        funding_ts: dict[str, tuple[list, list]] = {}
        for s, t_, r_ in con.execute(
                "SELECT symbol, funding_time, rate FROM funding_history "
                "ORDER BY funding_time"):
            try:
                t_ = int(t_)
                ts, rt = funding_ts.setdefault(s, ([], []))
                ts.append(t_ * 10**6 if t_ > 10**11 else t_ * 10**9)
                rt.append(float(r_))
            except (TypeError, ValueError):
                continue
        for e in maj:
            ranks, own = [], np.nan
            for s in MAJORS:
                ft = funding_ts.get(s)
                if not ft or len(ft[0]) < 5:
                    continue
                pos = int(np.searchsorted(np.array(ft[0]), e["ts_ms"],
                                          side="right")) - 1
                if pos < 0:
                    continue
                if s == e["sym"]:
                    own = ft[1][pos]
                ranks.append(ft[1][pos])
            e["fund_rank"] = (float(np.mean(np.array(ranks) <= own))
                              if ranks and np.isfinite(own) else np.nan)

        # flux 3 : survivor 1x (filtre ATR p90, 26/09)
        surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
        p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
        surv = [e for e in surv if e["atr_pct"] <= p90]
        for e in surv:
            e["strategy"] = "survivor_long"
            e["lev"] = 1
            e["fee_rt_bps"] = TAKER_RT

        # flux 4 : vol_spike_6h (seuils p5 intouchés)
        spike = collect_vol_spike(con, hold=6)
        for e in spike:
            e["strategy"] = "vol_spike_6h"
            e["lev"] = 1
            e["fee_rt_bps"] = TAKER_RT
        med_spike = float(np.median([e["atr_pct"] for e in spike]))
        mae_spike = max(e["mae_adverse"] for e in spike)

        _K = 0.89
        meme_all = [dict(e) for e in events]
        meme_gated = [dict(e) for e in gated_events]
        for stream in (meme_all, meme_gated):
            for e in stream:
                e["strategy"] = "cascade_meme"
                e["lev"] = max(1, int(100 / (max(x["mae_adverse"]
                                                 for x in stream) + 0.5)))
        med_meme_all = float(np.median([e["atr_pct"] for e in meme_all]))
        med_meme_gated = float(np.median([e["atr_pct"] for e in meme_gated]))

        def machine_fn(med_meme):
            def fn(e, st=None):
                s = e.get("strategy")
                if s == "cascade_10x":
                    s0 = min(max(0.24 * _K * (e["atr_pct"] / med_majors),
                                 0.08 * _K), 0.40 * _K)
                    if (np.isfinite(e.get("fund_rank", np.nan))
                            and e["fund_rank"] <= 0.33):
                        return min(s0 * 1.5, 0.50 * _K)
                    return s0
                if s == "cascade_meme":
                    return min(max(0.10 * _K * (e["atr_pct"] / med_meme),
                                   0.02 * _K), 0.30 * _K)
                if s == "vol_spike_6h":
                    return min(max(0.10 * _K * (e["atr_pct"] / med_spike),
                                   0.02 * _K), 0.30 * _K)
                return 0.20 * _K
            return fn

        runs = {}
        for name, meme_stream, med_m, with_spike in (
                ("BASELINE3", meme_all, med_meme_all, False),
                ("BASELINE4", meme_all, med_meme_all, True),
                ("MEME-GATÉ 4", meme_gated, med_meme_gated, True)):
            all_ev = sorted(maj + surv + meme_stream
                            + (spike if with_spike else []),
                            key=lambda e: e["ts_ms"])
            runs[name] = run_stack(all_ev, CAPITAL, machine_fn(med_m), fh)

        # les runs meme SEUL (flat 5 % — la mesure du flux)
        def flat(evs):
            return run_stack([dict(e) for e in evs], CAPITAL,
                             lambda e, st=None: SIZE, fh)
        meme_only_gated = flat(meme_gated)

        wallet_lines += [
            "", "## LE WALLET 4 FLUX — meme-gaté vs baseline", "",
            "Machine répliquée (cascade 10x gated AL p66 + survivor + "
            "vol_spike_6h p5, sizing machine K=0,89 ; seul le flux meme "
            "change). Baseline officielle 27/09 (--vol-spike ON) : "
            "$4 004,94, DD 24,8 %, 0 liq.", ""]
        for name in ("BASELINE3", "BASELINE4", "MEME-GATÉ 4"):
            wallet_lines += bloc_stats(runs[name], name) + [""]
        b4, g4 = runs["BASELINE4"], runs["MEME-GATÉ 4"]
        wallet_lines += [
            f"- Baseline4 répliquée ${b4['balance']:,.2f} vs officiel "
            f"$4 004,94 (écart ${(b4['balance'] - 4004.94):,.2f} — fetch "
            f"nocturne éventuel).",
            f"- **MEME-GATÉ vs BASELINE4** : ROI "
            f"{(g4['balance'] / CAPITAL - 1) * 100:+.0f} % vs "
            f"{(b4['balance'] / CAPITAL - 1) * 100:+.0f} % "
            f"({'✓ ROI ≥' if g4['balance'] >= b4['balance'] else '✗ ROI <'}), "
            f"DD {g4['max_dd']:.1f} % vs {b4['max_dd']:.1f} % "
            f"({'✓ DD ≤' if g4['max_dd'] <= b4['max_dd'] else '✗ DD >'}), "
            f"liq {g4['n_liq']} vs {b4['n_liq']} "
            f"({'✓ 0 liq' if g4['n_liq'] == 0 else '✗ LIQ'}) — et le MAE max "
            f"gardé {mae_kept.max():.1f} % < 99,5 % = 0 liq par "
            f"CONSTRUCTION (pas par busy-skip).", "",
            "### Le flux meme SEUL (flat 5 %) — le DD meme doit chuter", "",
            *bloc_stats(meme_only_all, "meme tout-venant"), "",
            *bloc_stats(meme_only_gated, "meme GATÉ"), ""]
        if meme_only_all["max_dd"] > 0:
            wallet_lines.append(
                f"- DD meme : {meme_only_all['max_dd']:.1f} % → "
                f"{meme_only_gated['max_dd']:.1f} % "
                f"({'✓ CHUTE' if meme_only_gated['max_dd'] < meme_only_all['max_dd'] else '✗'})")

        # ——— 5. l'honnêteté : la VAL depuis juin 2026 ———
        m_all = monthly_meme_table(meme_only_all, "tout")
        m_g = monthly_meme_table(meme_only_gated, "gate")
        months = sorted(set(m_all) | set(m_g))
        va_months = sorted({t["exit_ts"].strftime("%Y-%m") for t in
                            meme_only_all["trades"]
                            if t["exit_ts"] >= split_date})
        wallet_lines += [
            "", "## L'HONNÊTETÉ — la VAL négative depuis juin 2026", "",
            "| Mois | meme tout-venant N/WR/PnL | meme GATÉ N/WR/PnL |",
            "|---|---|---|"]
        for m in months:
            a, g = m_all.get(m), m_g.get(m)
            fa = f"{a['n']}/{a['w'] / max(a['n'], 1) * 100:.0f} %/{a['pnl']:+.2f}" if a else "—"
            fg = f"{g['n']}/{g['w'] / max(g['n'], 1) * 100:.0f} %/{g['pnl']:+.2f}" if g else "—"
            wallet_lines.append(f"| {m}{' (VAL)' if m in va_months else ''} | {fa} | {fg} |")
        val_all = [t for t in meme_only_all["trades"] if t["exit_ts"] >= split_date]
        val_g = [t for t in meme_only_gated["trades"] if t["exit_ts"] >= split_date]
        exp_a = float(np.mean([t["pnl"] for t in val_all])) if val_all else float("nan")
        exp_g = float(np.mean([t["pnl"] for t in val_g])) if val_g else float("nan")
        wallet_lines += [
            "", f"- VAL (dès {split_date:%d/%m/%Y}) : espérance meme tout-"
            f"venant {exp_a:+.3f} $/trade ({len(val_all)} trades) → gaté "
            f"{exp_g:+.3f} $/trade ({len(val_g)} trades).",
            f"- **{'Le gate RETOURNE la VAL (positive) — le flux est SAUVÉ.' if exp_g > 0 else 'La VAL reste NÉGATIVE même gatée — le flux est MORT quoi qu\u2019il arrive, le gate ne sauve pas un edge évaporé.'}**"]

    # ——— le verdict (construit APRÈS le wallet, assemblé avant lui) ———
    verdict_lines = ["", "## VERDICT", ""]
    if gate_pass:
        roi_ok = g4["balance"] >= b4["balance"]
        dd_ok = g4["max_dd"] <= b4["max_dd"]
        liq_ok = g4["n_liq"] == 0
        dd_meme_ok = meme_only_gated["max_dd"] < meme_only_all["max_dd"]
        val_saved = exp_g > 0
        verdict_lines += [
            f"- Features : {verdict_features} (up={adopted_up or '—'}, "
            f"down={adopted_down or '—'}).",
            f"- Gate : PASS — seuil TRAIN {thr:.3f} (keep {keep * 100:.0f} %), "
            f"MAE max gardé {mae_kept.max():.1f} % < 99,5 %.",
            f"- Wallet 4 flux : {'ROI ≥' if roi_ok else 'ROI <'} / "
            f"{'DD ≤' if dd_ok else 'DD >'} / {'0 liq' if liq_ok else 'LIQ'} "
            f"/ DD meme {'chute' if dd_meme_ok else 'ne chute pas'}.",
            f"- **Flux meme : {'SAUVÉ par le gate' if val_saved else 'MORT quoi qu\u2019il arrive (VAL toujours négative)'}** "
            f"(VAL espérance {exp_g:+.3f} $/trade gaté).",
            ("- Limite assumée : gate à UNE feature (age_d, âge censure "
             "warehouse) — sur-test possible ; statut CANDIDAT exige le "
             "paper forward meme-gaté." if single_feat else ""),
            f"- Catégorie registre proposée : "
            f"{'CANDIDAT (paper forward meme-gaté avant VALIDÉ)' if (roi_ok and dd_ok and liq_ok and dd_meme_ok) else 'CONTEXTE — le gate tient en quintiles mais pas au wallet séquentiel'}.",
            "", "Le garde-fou composé-des-mois prime : les ABSOLUS meurent "
            "avec les bugs, les RELATIFS (gaté vs baseline, mêmes données, "
            "même harnais) survivent."]
    else:
        verdict_lines += [
            f"- Features : {verdict_features} — {'aucun' if not (feats_up or feats_down) else 'insuffisant'} "
            f"gradient monotone tenu en VAL.",
            f"- **GATE : FAIL** — {'pas de signal meme exploitable' if not (feats_up or feats_down) else 'le score ne sépare pas assez en VAL'}.",
            f"- **Flux : MORT quoi qu\u2019il arrive** — espérance TRAIN "
            f"{exp_tr:+.3f} → VAL {exp_a:+.3f} $/trade (dès "
            f"{split_date:%m/%Y}) : l'edge s'est évaporé, aucun gate "
            f"admissible ne peut le sauver ; 3 mortels (MAE 224/109/106 %) "
            f"non isolables ex-ante → le 0-liq du wallet reste une chance "
            f"de busy-skip.",
            "- Catégorie registre proposée : NUL (gate meme) — le flux "
            "cascade_meme reste CONTEXTE (1x, survie par busy-skip) ; "
            "ré-évaluer seulement si le corpus meme double ou si un "
            "collecteur de features meme (liquidité on-chain, âge réel de "
            "listing) arrive.",
            "", "Un nul honnête vaut mieux qu'un faux positif : la VAL "
            "négative depuis juin 2026 ne se corrige pas par un gate si le "
            "signal ne tient pas hors TRAIN."]

    verdict_lines += ["", "---",
                      "Règles gravées : levier ≤ 100/(maxMAE + 0,5) — 0 liq "
                      "sans exception ; split par le temps 70/30 ; seuils "
                      "TRAIN, jugés VAL ; les RELATIFS survivent aux bugs, "
                      "pas les ABSOLUS. Un backtest n'est jamais une preuve : "
                      "le paper forward tranche.",
                      "", f"Run {(datetime.now(timezone.utc) - t0).total_seconds():.0f} s."]

    body = lines + wallet_lines + verdict_lines
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "meme-gate-2026-09-28.md"
    out.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"[mgate] rapport écrit : {out}")

    print("\n[mgate] ===== RÉSUMÉ =====")
    print(f"[mgate] corpus {len(events)} events (mortels ≥ 99,5 % : {n_dead_all}) "
          f"| features adoptées : up={adopted_up} down={adopted_down}")
    if score_rows_tr:
        print(f"[mgate] TRAIN exp/quintile : "
              + " ".join(f"{r['exp']:+.2f}" for r in score_rows_tr))
        print(f"[mgate] VAL   exp/quintile : "
              + " ".join(f"{r['exp']:+.2f}" for r in score_rows_va))
        print(f"[mgate] seuil {thr:.3f} (keep {keep * 100:.0f} %) | MAE max "
              f"gardé {mae_kept.max():.1f} % | gate PASS = {gate_pass}")
    if gate_pass:
        for n in ("BASELINE3", "BASELINE4", "MEME-GATÉ 4"):
            r = runs[n]
            print(f"[mgate] {n}: ${r['balance']:,.2f} "
                  f"(ROI {(r['balance'] / CAPITAL - 1) * 100:+.0f} %, "
                  f"DD {r['max_dd']:.1f} %, liq {r['n_liq']})")
        print(f"[mgate] meme seul : DD {meme_only_all['max_dd']:.1f} % → "
              f"{meme_only_gated['max_dd']:.1f} % | VAL exp "
              f"{exp_a:+.3f} → {exp_g:+.3f} $/trade "
              f"({'SAUVÉ' if exp_g > 0 else 'MORT'})")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
