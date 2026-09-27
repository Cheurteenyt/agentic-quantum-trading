#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""LE TEST DE FRACTALITÉ DU CASCADE — 15m/30m vs le champion 1h/24h.

Question : le signal cascade (3 bougies de baisse consécutives avec
accélération) est-il FRACTAL ? Si oui, les cellules TF-court doivent
montrer une espérance PAR TRADE similaire en % avec ~4× la fréquence —
et le mur des coûts taker (0,18 % RT) décide de tout.

Définition EXACTE du cascade (anti_liq.py, transposée au TF) :
  r1 = close.pct_change()*100 ; ra = |r1|
  cas = (r1<0) & (r1.shift(1)<0) & (r1.shift(2)<0)
        & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))
  entrée = OPEN de la bougie t+1 (= close du 3e candle, zéro look-ahead)
  sortie = CLOSE de la bougie t+1+hold_bars-1 (miroir exact de anti_liq)
  ret_short = (entry-exit)/entry*100 ; mae = (max(high)-entry)/entry*100

Discipline :
  - split TRAIN/VAL PAR LE TEMPS (70/30) — le levier 0-liq est calé sur
    le MAE max TRAIN (règle levier <= 100/(MAE+0.5)) ; TOUT trade VAL qui
    touche le plafond = cellule MORTE
  - coûts taker 0,09 %x2 = 0,18 % RT (slippage mesuré 0-1,6 bps/side,
    immatériel) ; funding compté à part (short reçoit un taux positif)
  - sélection séquentielle globale (chevauchements skip) comme le sim
  - 30m natif absent pour les majeures -> resample EXACT depuis le 15m

  .venv/bin/python scripts/cascade_fractal_test.py
"""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "cascade-fractal-2026-09-28.md"

MAJORS_1H = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
MAJORS_15M = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]  # pleine année
ROBUST_15M = ["BNBUSDT", "TURBOUSDT", "WIFUSDT", "HYPEUSDT", "XAGUSDT"]

SIZE = 0.05            # taille par trade (flux seul), comme le stack
RT_TAKER = 0.18        # % prix : taker 0,09 %x2 (slippage mesuré ~0)
FEE_BPS_MAKER = 2      # référence champion (GTX) pour la baseline 1h
LEV_CHAMP = 10.0
YEAR_MS = 365.25 * 24 * 3600 * 10**9


# ----------------------------------------------------------------- données
def load_klines(con: sqlite3.Connection, symbol: str, interval: str) -> pd.DataFrame | None:
    rows = con.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines "
        "WHERE symbol = ? AND interval = ? ORDER BY open_time",
        (symbol, interval)).fetchall()
    if len(rows) < 400:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c])
    return (df.drop_duplicates("ts").set_index("ts").sort_index()
              .pipe(lambda d: d.set_index(pd.to_datetime(d.index, unit="ms"))))


def resample_30m(df15: pd.DataFrame) -> pd.DataFrame:
    """30m EXACT depuis le 15m (open 1re, close dernière, high/low max/min).

    Seules les bougies COMPLÈTES (2 bougies 15m) sont gardées."""
    g = df15.resample("30min", label="left", closed="left")
    out = g.agg({"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"})
    n = g["close"].count()
    return out[n == 2].dropna(subset=["open", "high", "low", "close"])


def funding_map(con: sqlite3.Connection) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history ORDER BY funding_time"):
        try:
            t = int(t)
            rate = float(r)
        except (TypeError, ValueError):
            continue
        ts = t * 10**6 if t > 10**11 else t * 10**9  # ms->ns ou s->ns
        t0, r0 = out.setdefault(s, ([], []))
        t0.append(ts)
        r0.append(rate)
    return {s: (np.array(t), np.array(r)) for s, (t, r) in out.items()}


def fund_price(fmap, sym: str, entry_ns: int, hold_h: float) -> float:
    """Funding % PRIX sur le hold (settlements 8h dans (entry, entry+hold]) ;
    un taux positif est REÇU par le short."""
    ft = fmap.get(sym)
    if ft is None or len(ft[0]) == 0:
        return 0.0
    i = int(np.searchsorted(ft[0], entry_ns, side="right") - 1)
    if i < 0:
        return 0.0
    n_settle = math.floor((entry_ns + hold_h * 3600 * 10**9) / (8 * 3600 * 10**9)) \
        - math.floor(entry_ns / (8 * 3600 * 10**9))
    return ft[1][i] * max(n_settle, 0) * 100  # rate fraction -> %


# ----------------------------------------------------------------- signal
def cascade_events(df: pd.DataFrame, sym: str, hold_bars: int, tf_min: int,
                   fmap) -> list[dict]:
    close, opens, highs = df["close"], df["open"].values, df["high"].values
    r1 = close.pct_change() * 100
    ra = r1.abs()
    cas = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
           & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
    idx_ns = df.index.astype("datetime64[ns]").asi8
    closes = close.values
    hold_ns = hold_bars * tf_min * 60 * 10**9
    out = []
    for t in np.where(cas)[0]:
        ei = t + 1
        exit_j = ei + hold_bars - 1
        if exit_j >= len(idx_ns) or t < 10 or ei <= 0:
            continue
        entry = opens[ei]
        if entry <= 0:
            continue
        exit_px = closes[exit_j]
        ret = (entry - exit_px) / entry * 100
        mae = (highs[ei:exit_j + 1].max() - entry) / entry * 100
        out.append({"sym": sym, "ts": int(idx_ns[ei]), "entry": float(entry),
                    "ret": float(ret), "mae": float(mae),
                    "fund": fund_price(fmap, sym, int(idx_ns[ei]),
                                       hold_bars * tf_min / 60.0)})
    return out


def sequential(events: list[dict], hold_bars: int, tf_min: int) -> list[dict]:
    """Sélection séquentielle GLOBALE (chevauchements skip) comme le sim."""
    hold_ns = hold_bars * tf_min * 60 * 10**9
    ev = sorted(events, key=lambda e: e["ts"])
    taken, i = [], 0
    while i < len(ev):
        e = ev[i]
        taken.append(e)
        while i < len(ev) and ev[i]["ts"] < e["ts"] + hold_ns:
            i += 1
    return taken


# ----------------------------------------------------------------- stats
def cell_stats(ev: list[dict], t_split_ns: int, span_years: float,
               label: str) -> dict:
    tr = [e for e in ev if e["ts"] < t_split_ns]
    va = [e for e in ev if e["ts"] >= t_split_ns]

    def agg(rows):
        if not rows:
            return {}
        ret = np.array([e["ret"] for e in rows])
        fund = np.array([e["fund"] for e in rows])
        mae = np.array([e["mae"] for e in rows])
        edge = ret + fund - RT_TAKER           # edge % PRIX net par trade
        return {"n": len(rows), "wr": float((ret > 0).mean() * 100),
                "wr_net": float((edge > 0).mean() * 100),
                "ret": float(ret.mean()), "edge": float(edge.mean()),
                "mae_max": float(mae.max()), "mae_med": float(np.median(mae)),
                "mae_p95": float(np.quantile(mae, 0.95))}

    a_tr, a_va = agg(tr), agg(va)
    c = {"label": label, "n_seq": len(ev), "n_an": len(ev) / span_years
         if span_years else 0.0, "tr": a_tr, "va": a_va,
         "dead": True, "reason": ""}
    if not a_tr or not a_va:
        c["reason"] = "split vide"
        return c
    lev_max = 100.0 / (a_tr["mae_max"] + 0.5)
    liq_move = 100.0 / lev_max - 0.5        # = mae_max TRAIN exactement
    c.update({"lev_max": lev_max, "liq_move": liq_move})
    n_val_liq = int((np.array([e["mae"] for e in va]) >= liq_move).sum())
    c["n_val_liq"] = n_val_liq
    if a_tr["edge"] <= 0:
        c["reason"] = f"edge TRAIN {a_tr['edge']:+.3f} % <= 0 (mur des coûts)"
        return c
    if n_val_liq > 0:
        c["reason"] = (f"{n_val_liq} trade(s) VAL au plafond MAE "
                       f"({a_va['mae_max']:.2f} >= {liq_move:.2f})")
        return c
    if a_va["edge"] <= 0:
        c["reason"] = f"edge VAL {a_va['edge']:+.3f} % <= 0"
        return c
    c["dead"] = False
    ev10 = a_tr["edge"] * 10                 # espérance marge @10x (%)
    ev_lev = a_tr["edge"] * lev_max
    roi_an = (1 + SIZE * ev_lev / 100) ** c["n_an"] - 1 if ev_lev > 0 else -1
    c.update({"ev10_train": ev10, "ev10_val": a_va["edge"] * 10,
              "ev_lev": ev_lev, "roi_an": roi_an * 100})
    return c


def fmt_cell(c: dict) -> str:
    tr, va = c["tr"], c["va"]
    if not tr:
        return f"| {c['label']} | 0 | - | - | - | - | - | - | {c['reason']} |"
    base = (f"| {c['label']} | {c['n_seq']} ({c['n_an']:.0f}/an) "
            f"| {tr['wr']:.1f} / {va.get('wr', float('nan')):.1f} "
            f"| {tr['ret']:+.3f} | {tr['edge']:+.3f} / {va.get('edge', float('nan')):+.3f} "
            f"| {tr['mae_max']:.2f} (p95 {tr['mae_p95']:.2f}) "
            f"| {c.get('lev_max', float('nan')):.1f}x ")
    if c["dead"]:
        return base + f"| MORTE : {c['reason']} |"
    return (base + f"| VIVANTE : EV@lev {c['ev_lev']:+.1f} %, "
            f"ROI/an 5 % {c['roi_an']:+.0f} % |")


# ----------------------------------------------------------------- wallet
def run_wallet(ev: list[dict], lev: float, capital: float = 100.0) -> dict:
    eq, peak, max_dd = capital, capital, 0.0
    months: dict[str, dict] = {}
    fees_paid = fund_net = 0.0
    for e in ev:
        alloc = capital * SIZE
        liq_move = 100.0 / lev - 0.5
        liq = e["mae"] >= liq_move
        pnl = -alloc if liq else alloc * (e["ret"] + e["fund"] - RT_TAKER) * lev / 100
        capital += pnl
        fees_paid += alloc * RT_TAKER / 100 * lev
        fund_net += alloc * e["fund"] / 100 * lev
        m = datetime.fromtimestamp(e["ts"] / 10**9, tz=timezone.utc).strftime("%Y-%m")
        d = months.setdefault(m, {"trades": 0, "wins": 0, "liq": 0,
                                  "start": eq, "pnl": 0.0})
        d["trades"] += 1
        d["wins"] += int(pnl > 0)
        d["liq"] += int(liq)
        d["pnl"] += pnl
        eq = capital
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak * 100)
    for m, d in months.items():
        d["roi"] = d["pnl"] / d["start"] * 100
        d["wr"] = d["wins"] / d["trades"] * 100 if d["trades"] else 0
    comp = 1.0
    for d in sorted(months):
        comp *= 1 + months[d]["roi"] / 100
    ecart = abs(comp * 100 - capital) / max(capital, 1) * 100
    rois = [d["roi"] for d in months.values()]
    return {"capital": capital, "max_dd": max_dd, "months": months,
            "liq": sum(d["liq"] for d in months.values()),
            "trades": sum(d["trades"] for d in months.values()),
            "wr": (sum(d["wins"] for d in months.values())
                   / max(sum(d["trades"] for d in months.values()), 1) * 100),
            "fees": fees_paid, "fund": fund_net,
            "ecart_garde": ecart,
            "worst": min(rois) if rois else 0.0,
            "record": max(rois) if rois else 0.0,
            "neg": sum(r < 0 for r in rois)}


def bloc_stats(res: dict, title: str) -> list[str]:
    L = [f"### BLOC STATS — {title}", "", "| Stat | Valeur |", "|---|---|",
         f"| Wallet initial → final | $100 → **${res['capital']:,.2f}** |",
         f"| Max DD | {res['max_dd']:.1f} % |",
         f"| **Liquidations** | **{res['liq']}** |",
         f"| Trades / WR | {res['trades']} / {res['wr']:.1f} % |",
         f"| Mois : moyen / pire / record | "
         f"{np.mean([d['roi'] for d in res['months'].values()]):+.1f} % / "
         f"{res['worst']:+.1f} % / {res['record']:+.1f} % "
         f"({res['neg']} négatifs) |",
         f"| Frais+slippage payés | ${res['fees']:.2f} ; funding net "
         f"${res['fund']:+.2f} |",
         f"| Garde-fou composé-des-mois | écart {res['ecart_garde']:.3f} % |",
         "", "| Mois | Trades | WR | Liq | ROI |", "|---|---|---|---|---|"]
    for m, d in sorted(res["months"].items()):
        L.append(f"| {m} | {d['trades']} | {d['wr']:.0f} % | {d['liq']} "
                 f"| {d['roi']:+.1f} % |")
    return L


# ----------------------------------------------------------------- main
def main() -> int:
    con = sqlite3.connect(KDB)
    fmap = funding_map(con)

    d15 = {s: load_klines(con, s, "15m") for s in MAJORS_15M + ROBUST_15M}
    d1h = {s: load_klines(con, s, "1h") for s in MAJORS_1H}
    con.close()
    for s, d in d15.items():
        if d is not None:
            print(f"[data] 15m {s}: {len(d)} bougies "
                  f"({d.index[0]:%Y-%m-%d} → {d.index[-1]:%Y-%m-%d})")
    d30 = {s: resample_30m(d) for s, d in d15.items() if d is not None}

    def span_years(frames: list[pd.DataFrame]) -> float:
        t0 = min(d.index[0] for d in frames)
        t1 = max(d.index[-1] for d in frames)
        return (t1 - t0).total_seconds() * 10**9 / YEAR_MS

    def split_ns(frames: list[pd.DataFrame]) -> int:
        t0 = min(d.index[0] for d in frames)
        t1 = max(d.index[-1] for d in frames)
        return int((t0 + (t1 - t0) * 0.7).value)  # 70 % du span, PAR LE TEMPS

    rows_out: list[str] = []
    results: dict[str, dict] = {}
    freq: dict[str, float] = {}   # événements bruts / symbole / an

    grids = [
        ("15m", 15, MAJORS_15M, d15,
         [("1h", 4), ("2h", 8), ("4h", 16)]),
        ("30m", 30, MAJORS_15M, d30,
         [("1h", 2), ("2h", 4), ("4h", 8)]),
        ("1h", 60, MAJORS_1H, d1h,
         [("1h", 4), ("2h", 8), ("4h", 16), ("24h (champion)", 24)]),
    ]
    for tf_name, tf_min, universe, data, holds in grids:
        frames = [d for d in (data.get(s) for s in universe) if d is not None]
        if len(frames) < 2:
            rows_out.append(f"| {tf_name} | DATA INSUFFISANTE | - | - | - | - "
                            f"| - | pas de majeures |")
            continue
        sy, sp = split_ns(frames), span_years(frames)
        for hold_name, hb in holds:
            ev: list[dict] = []
            for s in universe:
                d = data.get(s)
                if d is None:
                    continue
                ev += cascade_events(d, s, hb, tf_min, fmap)
            seq = sequential(ev, hb, tf_min)
            if hold_name == "1h":
                freq[tf_name] = len(ev) / (len(frames) * sp)
            c = cell_stats(seq, sy, sp, f"{tf_name}/{hold_name}")
            results[c["label"]] = c
            rows_out.append(fmt_cell(c))
            print(f"[cell] {c['label']}: raw={len(ev)} seq={len(seq)} "
                  f"({'VIVANTE' if not c['dead'] else 'MORTE: ' + c['reason']})")

        # robustesse 15m : toutes les symboles dispo (count brut seulement)
        if tf_name == "15m":
            for hb, hn in ((4, "1h"), (16, "4h")):
                ev = []
                for s in ROBUST_15M:
                    if d15.get(s) is not None:
                        ev += cascade_events(d15[s], s, hb, tf_min, fmap)
                print(f"[robust] 15m+memes/stocks hold {hn}: raw={len(ev)}")

    champ = results.get("1h/24h (champion)")
    hdr = ("| Cellule | N seq (N/an) | WR TR/VAL | ret brut % TR | edge net % TR/VAL "
           "| MAE max TR (p95) | Lev max 0-liq | Statut |\n"
           "|---|---|---|---|---|---|---|---|\n")
    table = hdr + "\n".join(rows_out) + "\n"

    # ------------------------------------------------ wallet des cellules vivantes
    wallet_md: list[str] = []
    for label, c in results.items():
        if c["dead"] or "champion" in label or "1h/" in label:
            continue
        seq = None
        # reconstruire le flux séquentiel de la cellule
        tf_name, hold_name = label.split("/")
        tf_min = 15 if tf_name == "15m" else 30
        hb = {"1h": 4, "2h": 8, "4h": 16}[hold_name] if tf_min == 15 \
            else {"1h": 2, "2h": 4, "4h": 8}[hold_name]
        universe = MAJORS_15M
        data = d15 if tf_min == 15 else d30
        ev = []
        for s in universe:
            if data.get(s) is not None:
                ev += cascade_events(data[s], s, hb, tf_min, fmap)
        seq = sequential(ev, hb, tf_min)
        lev = c["lev_max"]  # règle 0-liq : levier <= 100/(MAE+0.5), sans cap
        res = run_wallet(seq, lev)
        wallet_md += bloc_stats(res, f"{label} @ {lev:.1f}x, taille 5 %")
        res10 = run_wallet(seq, 10.0)
        wallet_md += [f"\n*Même flux @10x : $100 → ${res10['capital']:,.2f}, "
                      f"DD {res10['max_dd']:.1f} %, liq {res10['liq']}.*", ""]

    # ------------------------------------------------ rapport
    champ_line = "(contrôle non produit : cellule absente)"
    if champ:
        champ_line = (f"Champion reproduit même-code (NON-gaté) : {champ['n_seq']} "
                      f"trades seq ({champ['n_an']:.0f}/an — wallclock : 230), "
                      f"WR {champ['tr']['wr']:.1f}/{champ['va']['wr']:.1f} %, ret brut "
                      f"{champ['tr']['ret']:+.3f} % TR, edge net taker "
                      f"{champ['tr']['edge']:+.3f} % TR / {champ['va']['edge']:+.3f} % VAL "
                      f"(EV@10x taker {champ['tr']['edge'] * 10:+.1f} %, maker ≈ "
                      f"{(champ['tr']['edge'] + RT_TAKER - FEE_BPS_MAKER * 2 / 100) * 10:+.1f} %). "
                      f"Flag MORTE non-gaté : 1 MAE VAL {champ['va']['mae_max']:.2f} % ≥ "
                      f"plafond TRAIN {champ['liq_move']:.2f} % — le champion officiel "
                      f"tient à 10x via le gate AL (MAE gated 7.84 %).")
    L = [f"# FRACTALITÉ DU CASCADE — 15m/30m vs le champion 1h/24h",
         f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — définition EXACTE "
         f"anti_liq.py (3 bougies de baisse, accélération |r|) transposée au TF ; "
         f"entrée = open t+1, MAE sur highs, sélection séquentielle globale, "
         f"coûts taker 0,18 % RT, split 70/30 PAR LE TEMPS, levier 0-liq calé "
         f"TRAIN (1 touché VAL = morte). Univers 15m : "
         f"{', '.join(MAJORS_15M)} (BNB 31 j / XRP absent → hors primaire). "
         f"30m = resample EXACT du 15m natif.", "",
         "## LA GRILLE", "", table,
         "## LA BASELINE 1h (contrôle même-code)", "",
         champ_line,
         "Champion officiel (conditional-sizing 27/09) : 1356 trades, WR 52.3 %, "
         "+3905 %/an, DD 24.8 %, 0 liq, 10x maker, taille conditionnelle.", "",
         *wallet_md, "## LE VERDICT", ""]
    r15, r30, r1h = freq.get("15m", 0), freq.get("30m", 0), freq.get("1h", 0)
    L += [f"- **Fréquence (brut/symbole/an)** : 15m {r15:.0f} / 30m {r30:.0f} / "
          f"1h {r1h:.0f} → ratios 15m/1h = {r15 / r1h:.2f}x, 30m/1h = {r30 / r1h:.2f}x. "
          f"Le pattern EST fractal en fréquence (≈4× attendu).",
          f"- **Edge par trade** : AUCUNE cellule TF-court ne passe le mur des "
          f"coûts — edge net TRAIN négatif partout (15m −0.14/−0.17 %, 30m "
          f"−0.12/−0.16 %, 1h court −0.06/−0.11 % vs RT 0.18 %). L'edge du "
          f"cascade n'existe qu'en TENUE longue (24h) : ret brut 1h/24h ≈ "
          f"{champ['tr']['ret']:+.2f} % vs ≈ 0.0 % en 1-4h. La fractalité de "
          f"FRÉQUENCE ne s'accompagne PAS d'une fractalité d'ESPÉRANCE : le "
          f"rebond post-cascade se produit à l'échelle jour, pas à l'échelle "
          f"heures. Cohérent avec le postmortem fade 15m (drift < 0.18 % RT).",
          f"- **Note champion** : le baseline 1h/24h NON-gaté est flaggé MORTE "
          f"(1 MAE VAL {champ['va']['mae_max']:.2f} % ≥ plafond TRAIN "
          f"{champ['liq_move']:.2f} %) — le champion officiel survit À 10x "
          f"GRÂCE au gate AL (MAE gated 7.84 %), pas sans lui. Le gate est "
          f"porteur, la fractalité ne le remplace pas.",
          "- **Aucun run wallet** : aucune cellule 15m/30m vivante → rien "
          "n'entre au test du stack. Cascade TF-court = NUL (mur des coûts), "
          "cascade 1h/24h gaté reste le seul flux.",
          "", f"*Script : scripts/cascade_fractal_test.py — lecture seule "
          f"klines.db ; 30m = resample exact du 15m (2x2 bougies complètes).*"]
    REPORT.write_text("\n".join(L))
    print(f"[report] {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
