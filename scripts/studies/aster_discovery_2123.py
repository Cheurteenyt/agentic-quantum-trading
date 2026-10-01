#!/usr/bin/env python3
"""T21 — DECOUVERTE des edges sur les regimes 2021-2023, jugement 2024-2026.

L'inversion du split temporel : TRAIN = bull_2021H2 + bear_2022 + recovery_2023
(jamais vecus par la machine), VAL = 2024-01 -> 2026-09 (la fenetre connue).
Decouverte = familles CLASSIQUES au-dela des 6 strategies de la campagne :

  trend_short   : MA cross baissier -> short (exit cross-back, stop 3xATR)
  trend_long    : miroir long
  meanrev_bb    : bandes de Bollinger LARGES (fenetre 40-100h), fade, sortie mid
  breakout      : cassure Donchian N h, sortie canal oppose N/2 ou time-stop
  carry         : funding REEL (API Aster, cache reports/) — long financement
                  profond negatif / short positif extreme, funding accru 8 h
  momentum      : continuation court terme (12-48 h), seuil 1.5 sigma 30 j
  wick_retrace  : fade des meches de liquidation (fraction de range)
  sma_regime    : filtre SMA journalier classique (50/100/200 j), long only

GRILLE GELÉE avant tout résultat (pré-enregistrement, anti-pêche VAL) :
trend 3 grilles, meanrev 3, breakout 3, carry 3, momentum 3, wick 3, sma 3.
Le VAL juge UNE FOIS — aucune itération de paramètre sur 2024+.

Execution : signal calcule au close t -> entree a l'open t+1 ; stop/take
intrabar (stop PRIORITAIRE si les deux touches), sortie signalee a l'open
suivant ; couts taker 4 bps/jambe (8 bps RT, modele Aster en vigueur) ;
position 1x, retour en % — verdicts RELATIFS. maxMAE -> plafond de levier
regle 0-liquidation lev <= 100/(maxMAE+0.5).

  .venv/bin/python scripts/studies/aster_discovery_2123.py
  .venv/bin/python scripts/studies/aster_discovery_2123.py --famille carry --write
  .venv/bin/python scripts/studies/aster_discovery_2123.py --no-funding-fetch

Sortie : rapport console + reports/aster_discovery_2123.md (--write) +
reports/aster_discovery_2123_raw.json. DB klines.db en READ-ONLY.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

STUDIES_DIR = Path(__file__).resolve().parent
ROOT = STUDIES_DIR.parents[1]

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "aster_discovery_2123.md"
RAW = ROOT / "reports" / "aster_discovery_2123_raw.json"
FUND_CACHE = ROOT / "reports" / "aster_discovery_2123_funding.json"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVAL = "1h"
COST_RT = 0.0008          # 4 bps taker/jambe (modele Aster), aller-retour
ATR_N = 24                # ATR 24 h
DAY_MS = 86_400_000

# --- Regimes (definitions T9, bornes UTC inclusives) -------------------------
TRAIN_REGIMES = [
    ("bull21",   "2021-09-01", "2021-12-31"),
    ("bear22",   "2022-01-01", "2022-12-31"),
    ("recov23",  "2023-01-01", "2023-12-31"),
]
VAL_REGIMES = [
    ("bull24",   "2024-01-01", "2024-06-30"),
    ("chop24",   "2024-07-01", "2024-12-31"),
    ("connu2526", "2025-01-01", "2026-09-30"),
]
ALL_REGIMES = TRAIN_REGIMES + VAL_REGIMES

# --- Grille GELÉE (pré-enregistrement) --------------------------------------
# Chaque config : (nom, famille, params)
CONFIGS = []
for f, s in [("trend_short", "short"), ("trend_long", "long")]:
    for g in [(20, 100), (10, 50), (50, 200)]:
        CONFIGS.append((f"{f}_ema{g[0]}x{g[1]}", f, {"fast": g[0], "slow": g[1], "side": s}))
for w, k in [(40, 2.5), (100, 3.0), (60, 2.5)]:
    CONFIGS.append((f"meanrev_bb{w}_{k}", "meanrev_bb", {"win": w, "k": k}))
for n in [24, 72, 168]:
    CONFIGS.append((f"breakout_don{n}", "breakout", {"n": n}))
# carry : (seuil_long bps/8h, seuil_short bps/8h, hold h) + 1 config quantiles
CONFIGS.append(("carry_thr-0.5+2.0_h48", "carry", {"lo": -0.5, "hi": 2.0, "hold": 48, "q": False}))
CONFIGS.append(("carry_thr-1.0+3.0_h72", "carry", {"lo": -1.0, "hi": 3.0, "hold": 72, "q": False}))
CONFIGS.append(("carry_q10q90_h24", "carry", {"lo": None, "hi": None, "hold": 24, "q": True}))
for lb in [12, 24, 48]:
    CONFIGS.append((f"momentum_lb{lb}", "momentum", {"lb": lb, "thr": 1.5}))
for frac, hold in [(0.55, 8), (0.65, 12), (0.60, 16)]:
    CONFIGS.append((f"wick_f{frac}_h{hold}", "wick_retrace", {"frac": frac, "hold": hold}))
for d in [50, 100, 200]:
    CONFIGS.append((f"sma_regime_{d}d", "sma_regime", {"days": d}))

# Fallback funding (modele T9, bps/8h) si l'API/cache est indisponible.
FUND_MODEL_BPS_8H = {"bull21": 2.0, "bear22": -0.5, "recov23": 0.5,
                     "bull24": 1.5, "chop24": 0.5, "connu2526": 0.3}

MIN_N = 15          # n minimal par regime pour dire "edge decouvert"
MIN_EDGE_BPS = 100  # cumul minimal (1 %) sur le regime pour dire "decouvert"


def log(msg: str) -> None:
    print(msg, flush=True)


def date_ms(s: str) -> int:
    return int(datetime.fromisoformat(s + "T00:00:00+00:00").timestamp() * 1000)


def regime_of(ts_ms: int) -> str:
    for name, a, b in ALL_REGIMES:
        if date_ms(a) <= ts_ms <= date_ms(b) + DAY_MS - 1:
            return name
    return "hors"


# ---------------------------------------------------------------- funding API
def fetch_funding(symbols: list[str]) -> dict[str, list]:
    """Funding REEL Aster depuis la genese (fenetres <= 29 j, piege T4),
    pacing 1.45 s, cache JSON dans reports/ (ecriture autorisee)."""
    from curl_cffi import requests as creq

    if FUND_CACHE.exists():
        data = json.loads(FUND_CACHE.read_text())
        if all(s in data and data[s] for s in symbols):
            log(f"[funding] cache {FUND_CACHE.name} utilise ({sum(len(v) for v in data.values())} events)")
            return data
    out: dict[str, list] = {}
    t0 = time.time()
    for s in symbols:
        ev: list[tuple[int, float]] = []
        start = date_ms("2021-08-20")
        end_now = int(time.time() * 1000)
        while start < end_now:
            stop = min(start + 29 * DAY_MS, end_now)
            r = creq.get("https://fapi.asterdex.com/fapi/v3/fundingRate",
                         params={"symbol": s, "startTime": start, "endTime": stop,
                                 "limit": 1000}, impersonate="chrome131", timeout=20)
            if r.status_code != 200:
                log(f"[funding] {s} {r.status_code} sur fenetre {start} — fenetre perdue")
            else:
                for x in r.json():
                    ev.append((int(x["fundingTime"]), float(x["fundingRate"])))
            start = stop
            time.sleep(1.45)
        ev.sort()
        seen: set[int] = set()
        ev = [x for x in ev if not (x[0] in seen or seen.add(x[0]))]  # frontières inclusives
        out[s] = ev
        log(f"[funding] {s}: {len(ev)} events ({len(ev) and datetime.fromtimestamp(ev[0][0]/1000, tz=timezone.utc)} -> {len(ev) and datetime.fromtimestamp(ev[-1][0]/1000, tz=timezone.utc)})")
    FUND_CACHE.write_text(json.dumps(out))
    log(f"[funding] cache ecrit en {time.time()-t0:.0f}s -> {FUND_CACHE.name}")
    return out


# ------------------------------------------------------------------- loading
def load_klines(con: sqlite3.Connection, symbol: str) -> pd.DataFrame:
    rows = con.execute(
        "SELECT open_time, open, high, low, close FROM klines "
        "WHERE symbol=? AND interval=? ORDER BY open_time", (symbol, INTERVAL)).fetchall()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    return df


def atr(df: pd.DataFrame, n: int = ATR_N) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ------------------------------------------------------------------ indicators
def build_signals(df: pd.DataFrame, fam: str, p: dict, fund_df: pd.DataFrame | None) -> dict:
    """Pre-calcule les tableaux de signaux : entree long/short au close t,
    exit (cross/time gere au moteur), stops."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    sig = {"long": np.zeros(len(df), bool), "short": np.zeros(len(df), bool)}
    a = atr(df)
    sig["atr"] = a.fillna(np.inf).values
    sig["hold"] = None       # time-stop en barres (None = pas de time-stop)
    sig["stop_atr"] = 3.0
    sig["exit_long"] = np.zeros(len(df), bool)
    sig["exit_short"] = np.zeros(len(df), bool)

    if fam in ("trend_short", "trend_long"):
        fast = c.ewm(span=p["fast"], adjust=False).mean()
        slow = c.ewm(span=p["slow"], adjust=False).mean()
        up, dn = fast > slow, fast < slow
        cross_dn = dn & ~dn.shift(1, fill_value=False)
        cross_up = up & ~up.shift(1, fill_value=False)
        if p["side"] == "short":
            sig["short"] = (cross_dn | dn).values & a.notna().values
            sig["exit_short"] = up.values      # exit a l'open suivant
        else:
            sig["long"] = (cross_up | up).values & a.notna().values
            sig["exit_long"] = dn.values
        sig["hold"] = None
    elif fam == "meanrev_bb":
        mid = c.rolling(p["win"]).mean()
        sd = c.rolling(p["win"]).std()
        lo, hi = mid - p["k"] * sd, mid + p["k"] * sd
        ok = a.notna() & mid.notna()
        sig["long"] = (c < lo).values & ok.values
        sig["short"] = (c > hi).values & ok.values
        sig["exit_long"] = (c >= mid).values    # retour a la moyenne
        sig["exit_short"] = (c <= mid).values
        sig["hold"] = 96
    elif fam == "breakout":
        n = p["n"]
        hh = h.rolling(n).max().shift(1)
        ll = l.rolling(n).min().shift(1)
        ok = a.notna() & hh.notna()
        sig["long"] = (c > hh).values & ok.values
        sig["short"] = (c < ll).values & ok.values
        m = max(n // 2, 4)
        hh2 = h.rolling(m).max().shift(1)
        ll2 = l.rolling(m).min().shift(1)
        sig["exit_long"] = (c < ll2).values
        sig["exit_short"] = (c > hh2).values
        sig["hold"] = 168
    elif fam == "momentum":
        ret = c.pct_change(p["lb"])
        s30 = ret.rolling(720).std()
        ok = a.notna() & s30.notna()
        sig["long"] = (ret > p["thr"] * s30).values & ok.values    # continuation
        sig["short"] = (ret < -p["thr"] * s30).values & ok.values
        sig["hold"] = 24
    elif fam == "wick_retrace":
        rng = (h - l).replace(0, np.nan)
        lw = (np.minimum(o, c) - l) / rng
        uw = (h - np.maximum(o, c)) / rng
        ok = a.notna() & (rng > 1.2 * a).values
        sig["long"] = ((lw >= p["frac"]).values & ok.values)
        sig["short"] = ((uw >= p["frac"]).values & ok.values)
        sig["hold"] = p["hold"]
    elif fam == "sma_regime":
        w = p["days"] * 24
        sma = c.rolling(w).mean()
        ok = sma.notna()
        sig["long"] = (c > sma).values & ok.values
        sig["exit_long"] = (c < sma).values
        sig["stop_atr"] = 10.0
        sig["hold"] = None
    elif fam == "carry":
        if fund_df is None:
            return None
        r = fund_df.set_index("t")["rate"]
        r = r[~r.index.duplicated(keep="first")].sort_index()  # frontières de fenêtres API
        f_h = r.reindex(df["ts"].values, method="ffill").fillna(0.0)  # bps/8h
        if p["q"]:
            rq = r[~r.index.duplicated(keep="first")].sort_index()
            q_lo = rq.rolling(90, min_periods=30).quantile(0.10)   # 30 j d'events 8h = 90
            q_hi = rq.rolling(90, min_periods=30).quantile(0.90)
            q_lo = q_lo.reindex(df["ts"].values, method="ffill")
            q_hi = q_hi.reindex(df["ts"].values, method="ffill")
            sig["long"] = (f_h.values <= q_lo.values)
            sig["short"] = (f_h.values >= q_hi.values)
        else:
            sig["long"] = (f_h.values <= p["lo"])
            sig["short"] = (f_h.values >= p["hi"])
        sig["hold"] = p["hold"]
        sig["stop_atr"] = 5.0
        sig["fund_bps8h"] = f_h.values
    else:
        raise ValueError(fam)
    return sig


# --------------------------------------------------------------------- engine
def run(df: pd.DataFrame, sig: dict, inverse: bool = False) -> list[dict]:
    """Moteur 1 h : entree open t+1, stop prioritaire intrabar, sortie a
    l'open suivant. Retourne les trades (net de 8 bps RT, funding pour carry)."""
    n = len(df)
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    enter_l = sig["long"] ^ inverse if inverse else sig["long"]
    enter_s = sig["short"] ^ inverse if inverse else sig["short"]
    ex_l, ex_s = sig["exit_long"], sig["exit_short"]
    hold, stop_atr = sig["hold"], sig["stop_atr"]
    atrv = sig["atr"]
    fund = sig.get("fund_bps8h")
    trades: list[dict] = []
    pos = 0
    entry_px = stop = entry_i = 0
    for i in range(1, n - 1):
        if pos == 0:
            if enter_l[i] and np.isfinite(atrv[i]):
                pos, entry_px, entry_i = 1, o[i + 1], i + 1
                stop = entry_px - stop_atr * atrv[i]
            elif enter_s[i] and np.isfinite(atrv[i]):
                pos, entry_px, entry_i = -1, o[i + 1], i + 1
                stop = entry_px + stop_atr * atrv[i]
            continue
        # gestion de la position ouverte (barre i >= entry_i)
        exit_px = None
        if pos == 1 and l[i] <= stop:
            exit_px = stop                      # stop prioritaire (conservateur)
        elif pos == -1 and h[i] >= stop:
            exit_px = stop
        elif i - entry_i >= (hold or 10**9):
            exit_px = o[i + 1]                  # time-stop -> open suivant
        elif (pos == 1 and ex_l[i]) or (pos == -1 and ex_s[i]):
            exit_px = o[i + 1]                  # signal de sortie -> open suivant
        if exit_px is None:
            continue
        gross = (exit_px / entry_px - 1) if pos == 1 else (entry_px / exit_px - 1)
        pnl = gross - COST_RT
        if fund is not None:
            # long PAIT un funding positif (signe : -pos * rate)
            pay = fund[entry_i:i + 1].sum() / 1e4
            pnl += -pos * pay
        if pos == 1:
            adverse = min(l[entry_i:i + 1]) / entry_px - 1
            mae = max(0.0, -adverse * 100.0)
        else:
            adverse = max(h[entry_i:i + 1]) / entry_px - 1   # meche adverse HAUTE
            mae = max(0.0, adverse * 100.0)
        trades.append({"ts": int(df["ts"].values[entry_i]), "dir": pos,
                       "ret": pnl * 100.0, "mae": mae})
        pos = 0
    return trades


# --------------------------------------------------------------------- stats
def stats(trades: list[dict]) -> dict | None:
    if not trades:
        return None
    r = np.array([t["ret"] for t in trades])
    eq = np.cumprod(1 + r / 100)
    peak = np.maximum.accumulate(eq)
    dd = float(((eq / peak) - 1).min() * 100)
    return {"n": len(trades), "wr": float((r > 0).mean() * 100),
            "sum": float(r.sum()), "med": float(np.median(r)),
            "worst": float(r.min()), "maxdd": dd,
            "maxmae": float(max(t["mae"] for t in trades))}


def monthly_block(trades: list[dict]) -> dict:
    months: dict[str, float] = {}
    for t in trades:
        m = datetime.fromtimestamp(t["ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")
        months[m] = months.get(m, 0.0) + t["ret"]
    vals = list(months.values())
    if not vals:
        return {}
    return {"mois_pos": sum(1 for v in vals if v > 0), "mois_neg": sum(1 for v in vals if v < 0),
            "best": max(vals), "worst": min(vals), "n_mois": len(vals)}


# ---------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--famille", default="all")
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--regime", default=None, help="filtre d'affichage")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--no-funding-fetch", action="store_true",
                    help="carry : cache uniquement, sinon modele T9 degrade")
    args = ap.parse_args()

    fams = None if args.famille == "all" else set(args.famille.split(","))
    symbols = [s for s in args.symbols.split(",") if s]
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    need_fund = fams is None or "carry" in fams
    fund_data: dict[str, list] = {}
    fund_mode = "modele_T9"
    if need_fund and not args.no_funding_fetch:
        try:
            fund_data = fetch_funding(symbols)
            fund_mode = "reel_API"
        except Exception as e:  # noqa: BLE001 — degrade honnetement
            log(f"[funding] echec ({e}) -> fallback modele T9 (carry DEGRADE)")
    elif need_fund:
        log("[funding] --no-funding-fetch -> modele T9 (carry DEGRADE)")

    data, fund_frames = {}, {}
    for s in symbols:
        data[s] = load_klines(con, s)
        log(f"[data] {s}: {len(data[s])} barres 1h "
            f"({datetime.fromtimestamp(data[s]['ts'].iloc[0]/1000, tz=timezone.utc):%Y-%m-%d} -> "
            f"{datetime.fromtimestamp(data[s]['ts'].iloc[-1]/1000, tz=timezone.utc):%Y-%m-%d})")
        if s in fund_data and fund_data[s]:
            fund_frames[s] = pd.DataFrame(fund_data[s], columns=["t", "rate"])
            fund_frames[s]["rate"] = fund_frames[s]["rate"] * 1e4  # bps/8h

    results = []
    for name, fam, p in CONFIGS:
        if fams is not None and fam not in fams:
            continue
        per_dir = {}
        for inv in (False, True):
            pooled: list[dict] = []
            for s in symbols:
                sig = build_signals(data[s], fam, p, fund_frames.get(s) if fund_mode == "reel_API" else None)
                if sig is None:
                    # fallback modele : funding constant par regime
                    ff = pd.DataFrame({"t": data[s]["ts"].values})
                    ff["rate"] = [FUND_MODEL_BPS_8H.get(regime_of(t), 0.3) for t in ff["t"]]
                    sig = build_signals(data[s], fam, p, ff)
                pooled.extend(run(data[s], sig, inverse=inv))
            per_dir[inv] = pooled
        by_reg: dict[str, list] = {}
        for t in per_dir[False]:
            by_reg.setdefault(regime_of(t["ts"]), []).append(t)
        by_reg_inv: dict[str, list] = {}
        for t in per_dir[True]:
            by_reg_inv.setdefault(regime_of(t["ts"]), []).append(t)
        row = {"cfg": name, "fam": fam, "stats": {}, "inv": {}}
        for reg, _a, _b in ALL_REGIMES:
            row["stats"][reg] = stats(by_reg.get(reg, []))
            row["inv"][reg] = stats(by_reg_inv.get(reg, []))
        row["all_trades"] = per_dir[False]
        row["monthly"] = monthly_block(per_dir[False])
        results.append(row)

    render(results, args, fund_mode)
    if args.write:
        RAW.write_text(json.dumps(
            [{"cfg": r["cfg"], "fam": r["fam"], "stats": r["stats"], "inv": r["inv"],
              "monthly": r["monthly"]} for r in results], indent=1))
        write_report(results, fund_mode)
        log(f"[write] {REPORT}\n[write] {RAW}")


def fmt(st: dict | None) -> str:
    if st is None:
        return "—"
    return f"{st['sum']:+.0f}@{st['n']} wr{st['wr']:.0f}%"


def render(results: list, args, fund_mode: str) -> None:
    log(f"\n=== T21 DECOUVERTE 2021-2023 (TRAIN) -> JUGEMENT 2024-2026 (VAL) | "
        f"funding: {fund_mode} | couts {COST_RT*1e4:.0f} bps RT ===")
    log(f"{'config':24} | {'bull21':>16} | {'bear22':>16} | {'recov23':>16} | {'VAL2426':>18} | inv(bear22/VAL)")
    for r in results:
        val = combine([r["stats"].get(x) for x, _a, _b in VAL_REGIMES])
        val_inv = combine([r["inv"].get(x) for x, _a, _b in VAL_REGIMES])
        b_inv = r["inv"].get("bear22")
        iv = f"{val_inv['sum']:+.0f}" if val_inv else "—"
        log(f"{r['cfg']:24} | {fmt(r['stats'].get('bull21')):>16} | {fmt(r['stats'].get('bear22')):>16} "
            f"| {fmt(r['stats'].get('recov23')):>16} | {fmt(val):>18} | {fmt(b_inv)}/{iv}")


def combine(stats_list: list) -> dict | None:
    ts = [s for s in stats_list if s]
    if not ts:
        return None
    n = sum(s["n"] for s in ts)
    return {"n": n, "wr": sum(s["wr"] * s["n"] for s in ts) / n,
            "sum": sum(s["sum"] for s in ts), "med": float(np.median([s["med"] for s in ts])),
            "worst": min(s["worst"] for s in ts), "maxdd": min(s["maxdd"] for s in ts),
            "maxmae": max(s["maxmae"] for s in ts)}


def write_report(results: list, fund_mode: str) -> None:
    L = ["# T21 — DECOUVERTE des edges 2021-2023, jugement 2024-2026", "",
         f"Date : {datetime.now(tz=timezone.utc):%Y-%m-%d %H:%M} UTC · One-shot : "
         "`scripts/studies/aster_discovery_2123.py` · DB `data/warehouse/klines.db` (ro) · "
         f"klines 1h BTC/ETH/SOL (T6) · funding : **{fund_mode}** · coûts taker 8 bps RT · "
         "exécution open t+1, stop prioritaire.", "",
         "Grille de paramètres **gelée avant exécution** (pré-enregistrement). Le VAL "
         "(2024-01→2026-09) juge UNE FOIS. `sum@n wr%` = cumul bps, trades, win-rate "
         "(pooled 3 symboles). inv = contrôle inverse (signe inversé).", ""]
    L.append("## 1. Table découverte — TRAIN par régime, VAL en jugement")
    L.append("")
    L.append("| config | bull21 | bear22 | recov23 | **VAL 24-26** | inv bear22 | inv VAL |")
    L.append("|---|---|---|---|---|---|---|")
    for r in results:
        val = combine([r["stats"].get(x) for x, _a, _b in VAL_REGIMES])
        val_inv = combine([r["inv"].get(x) for x, _a, _b in VAL_REGIMES])
        L.append(f"| `{r['cfg']}` | {fmt(r['stats'].get('bull21'))} | {fmt(r['stats'].get('bear22'))} "
                 f"| {fmt(r['stats'].get('recov23'))} | **{fmt(val)}** | {fmt(r['inv'].get('bear22'))} "
                 f"| {fmt(val_inv)} |")
    L.append("")
    L.append("## 2. Carte VAL par sous-régime (bull24 / chop24 / connu25-26)")
    L.append("")
    L.append("| config | bull24 | chop24 | connu25-26 |")
    L.append("|---|---|---|---|")
    for r in results:
        L.append(f"| `{r['cfg']}` | {fmt(r['stats'].get('bull24'))} | {fmt(r['stats'].get('chop24'))} "
                 f"| {fmt(r['stats'].get('connu2526'))} |")
    L.append("")
    L.append("## 3. Bloc mensuel (échantillon complet 2021-2026, pooled)")
    L.append("")
    L.append("| config | mois+ | mois- | record mois | pire mois |")
    L.append("|---|---|---|---|---|")
    for r in results:
        m = r["monthly"]
        if m:
            L.append(f"| `{r['cfg']}` | {m['mois_pos']} | {m['mois_neg']} | {m['best']:+.0f} bps "
                     f"| {m['worst']:+.0f} bps |")
    L.append("")
    L.append("## 4. Verdicts")
    verdicts = classify(results)
    for v in verdicts:
        L.append(v)
    REPORT.write_text("\n".join(L) + "\n")


def classify(results: list) -> list[str]:
    out = []
    val_regs = [x for x, _a, _b in VAL_REGIMES]
    for r in results:
        st, inv = r["stats"], r["inv"]
        best_reg, best = None, None
        for reg, _a, _b in TRAIN_REGIMES:
            s = st.get(reg)
            if s and s["n"] >= MIN_N and s["sum"] >= MIN_EDGE_BPS:
                if best is None or s["sum"] > best["sum"]:
                    best_reg, best = reg, s
        val = combine([st.get(x) for x in val_regs])
        val_inv = combine([inv.get(x) for x in val_regs])
        if best is None:
            tag = "NUL"
        else:
            inv_dom = val_inv and val and val_inv["sum"] > val["sum"]
            if val and val["sum"] > 0 and not inv_dom:
                tag = f"SURVIVANT (découvert en {best_reg})"
            else:
                tag = f"ARTEFACT DE RÉGIME (découvert en {best_reg}, meurt en VAL)"
        m = r["monthly"]
        mm = (f" mensuel: {m['mois_pos']}+/{m['mois_neg']}-" if m else "")
        out.append(f"- `{r['cfg']}` — **{tag}**{mm}")
    return out


if __name__ == "__main__":
    main()
