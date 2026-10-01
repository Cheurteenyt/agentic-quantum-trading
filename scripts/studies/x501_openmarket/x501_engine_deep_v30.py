#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OPÉRATION x501 — v30 : PORTAGE DEEP « depuis le début de l'actif ».

Moteur identique à x501_alpha_backtest.py (4 alphas, mêmes coûts, même
pipeline par barre 1h confirmée) SAUF la source de données et la timeline :
  - klines 1h + funding lus dans om_v27.db (tables bn_kline_1h_deep avec
    taker_buy, bn_funding_deep en secondes -> ms) — Binance fapi, 9 actifs ;
  - GRILLE GLOBALE = timeline BTC (listing 2019-09-08) ; chaque actif est
    actif à partir de SON listing (plancher deep) + warmup 60 j depuis son
    propre premier bar. Plus aucune assertion d'alignement inter-symboles.
Politique verrouillée (docs/37) : backtest TOUJOURS depuis le début de
l'actif — les flux s'ajoutent au portefeuille à mesure des listings.

Fidélité au moteur OpenMarket (fillModel="pessimistic", engine 3.0.63+) :
  pipeline par barre 1h confirmée :
    [funding] -> [exits protecteurs vs brackets] -> [exits signal au close préc.]
    -> [entries au marché à l'open] -> [contrôle liquidation] -> [script au close]
  - stop + TP touchés dans la même bougie 1h : le stop passe d'abord
  - marché/stop : taker 4,5 bps + slippage 2 bps ; TPs : maker 1,8 bps, sans slippage
  - brackets armés la bougie SUIVANT le remplissage ; funding réel Binance
  - les scripts H4 ne s'exécutent qu'aux closes 4h (comme un chart 4h sur la plateforme)

Écarts documentés (pas d'historique public) :
  - CVD = delta taker Binance ; liquidations indisponibles -> flux "cascade" d'A2
    réduit à la composante financement extrême (equivalent requireFlush=false)
  - open interest indisponible -> requireOi=false (A4)
Mode MESURE : coupe-circuit -25 % désactivé (maxDD brut rapporté ; les R-multiples
par trade sont invariants au sizing, donc réutilisables pour le Monte-Carlo).
"""
import bisect
import csv
import json
import math
import os
import pickle
import sqlite3
import datetime as dt
from dataclasses import dataclass, field

EXT_ROOT = os.environ.get("X501_EXT_ROOT", "/home/z/my-project")  # data deep locale, hors git (docs/26/37)
DB_PATH = f"{EXT_ROOT}/scripts/x501_v21_results/om_v27.db"
OUT = os.environ.get("X501_OUT", f"{EXT_ROOT}/scripts/x501_v21_results")
os.makedirs(OUT, exist_ok=True)

CFG = dict(
    initialCapital=100.0,
    riskPct=2.5,          # risque par trade (%) — palier de mesure
    riskCapPct=7.5,       # risque TOTAL engagé simultané (% de l'équité)
    maxEffLev=10.0,
    minNotional=5.0,
    minStopPct=0.6, maxStopPct=5.0,
    dailyStop=8.0, weeklyStop=15.0, killDD=None,   # killDD=None : mode mesure
    taker=0.00045, maker=0.00018, slip=0.0002,
    mmr=0.005, nomLev=10.0,
    trailLen=5, trailBufPct=0.5,          # trail H4 (5 barres 4h) pour A2/A3/A4
    stopBufPct=0.35,
)
SYMS = (os.environ.get("X501_SYMS", "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,BNBUSDT,"
        "DOGEUSDT,AVAXUSDT,LINKUSDT")).split(",")
ALPHAS = ["A1", "A2", "A3", "A4"]
B4 = 4 * 3600 * 1000
B1 = 3600 * 1000


# =============================== Données =====================================
def load_klines(symbol):
    """Klines 1h Binance deep depuis le listing (ts ms, OHLCV + volume taker)."""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT ts, open, high, low, close, volume, taker_buy "
        "FROM bn_kline_1h_deep WHERE symbol=? ORDER BY ts", (symbol,)).fetchall()
    con.close()
    if not rows:
        raise RuntimeError(f"aucune kline deep pour {symbol}")
    t = [r[0] for r in rows]
    o = [r[1] for r in rows]; h = [r[2] for r in rows]
    l = [r[3] for r in rows]; c = [r[4] for r in rows]
    v = [r[5] for r in rows]; tb = [r[6] if r[6] is not None else 0.0 for r in rows]
    return t, o, h, l, c, v, tb


def load_funding(symbol):
    """Funding deep Binance : ts en SECONDES dans la DB -> conversion ms."""
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("SELECT ts, rate FROM bn_funding_deep WHERE symbol=? "
                       "ORDER BY ts", (symbol,)).fetchall()
    con.close()
    arr = sorted((int(ts) * 1000, float(rate)) for ts, rate in rows)
    return arr


# ============================ Indicateurs de base ============================
def ema(series, period):
    out = [None] * len(series)
    if not series:
        return out
    alpha = 2.0 / (period + 1.0)
    acc = series[0]
    out[0] = acc
    for i in range(1, len(series)):
        acc = alpha * series[i] + (1 - alpha) * acc
        out[i] = acc
    return out


def sma(series, period):
    out = [None] * len(series)
    s = 0.0
    for i, x in enumerate(series):
        s += x
        if i >= period:
            s -= series[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def rsi(closes, period=14):
    out = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0); losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def wilder_adx(h, l, c, period=14):
    n = len(c)
    adx = [None] * n
    if n < 2 * period + 2:
        return adx
    tr_s = dm_p_s = dm_m_s = 0.0
    dxs = []
    prev_tr = prev_p = prev_m = None
    adx_prev = 0.0
    for i in range(1, n):
        up = h[i] - h[i - 1]; dn = l[i - 1] - l[i]
        dp = up if (up > dn and up > 0) else 0.0
        dm = dn if (dn > up and dn > 0) else 0.0
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if i <= period:
            tr_s += tr; dm_p_s += dp; dm_m_s += dm
            if i == period:
                prev_tr, prev_p, prev_m = tr_s, dm_p_s, dm_m_s
            continue
        prev_tr = prev_tr - prev_tr / period + tr
        prev_p = prev_p - prev_p / period + dp
        prev_m = prev_m - prev_m / period + dm
        dip = 100.0 * prev_p / prev_tr if prev_tr > 0 else 0.0
        dim = 100.0 * prev_m / prev_tr if prev_tr > 0 else 0.0
        dx = 100.0 * abs(dip - dim) / (dip + dim) if (dip + dim) > 0 else 0.0
        dxs.append(dx)
        if len(dxs) == period:
            a = sum(dxs) / period
            adx[i] = a
            adx_prev = a
        elif len(dxs) > period:
            adx_prev = (adx_prev * (period - 1) + dx) / period
            adx[i] = adx_prev
    return adx


def rolling_min(a, w):
    out = [None] * len(a)
    for i in range(len(a)):
        j0 = max(0, i - w + 1)
        seg = a[j0:i + 1]
        if len(seg) >= min(w, i + 1):
            out[i] = min(seg)
    return out


def rolling_max(a, w):
    out = [None] * len(a)
    for i in range(len(a)):
        j0 = max(0, i - w + 1)
        seg = a[j0:i + 1]
        if len(seg) >= min(w, i + 1):
            out[i] = max(seg)
    return out


def stdev(a, w):
    out = [None] * len(a)
    for i in range(len(a)):
        if i >= w - 1:
            seg = a[i - w + 1:i + 1]
            m = sum(seg) / w
            out[i] = math.sqrt(sum((x - m) ** 2 for x in seg) / w)
    return out


def wilder_atr(h, l, c, period=14):
    n = len(c)
    atr = [None] * n
    acc = 0.0
    for i in range(1, n):
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if i <= period:
            acc += tr
            if i == period:
                atr[i] = acc / period
        else:
            atr[i] = (atr[i - 1] * (period - 1) + tr) / period
    return atr


def stoch(h, l, c, pk=14, sk=3, sd=3):
    n = len(c)
    raw = [None] * n
    for i in range(n):
        if i >= pk - 1:
            hh = max(h[i - pk + 1:i + 1]); ll = min(l[i - pk + 1:i + 1])
            raw[i] = 100.0 * (c[i] - ll) / (hh - ll) if hh > ll else 50.0
    k = [None] * n
    for i in range(n):
        if i >= pk - 1 + sk - 1:
            seg = [x for x in raw[i - sk + 1:i + 1] if x is not None]
            if len(seg) == sk:
                k[i] = sum(seg) / sk
    d = [None] * n
    for i in range(n):
        if k[i] is not None and i >= sd - 1:
            seg = [x for x in k[i - sd + 1:i + 1] if x is not None]
            if len(seg) == sd:
                d[i] = sum(seg) / sd
    return k, d


def supertrend(h, l, c, factor=3.0, period=10):
    n = len(c)
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = [None] * n
    acc = 0.0
    for i in range(1, n):
        if i <= period:
            acc += tr[i]
            if i == period:
                atr[i] = acc / period
        else:
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    ub = [None] * n; lb = [None] * n; fub = [None] * n; flb = [None] * n
    direction = [None] * n
    for i in range(n):
        if atr[i] is None:
            continue
        mid = (h[i] + l[i]) / 2.0
        ub[i] = mid + factor * atr[i]
        lb[i] = mid - factor * atr[i]
        if i > 0 and fub[i - 1] is not None:
            fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
            flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
            if direction[i - 1] == 1:
                direction[i] = -1 if c[i] < flb[i] else 1
            else:
                direction[i] = 1 if c[i] > fub[i] else -1
        else:
            fub[i] = ub[i]; flb[i] = lb[i]
            direction[i] = 1 if c[i] >= mid else -1
    return direction


# ==================== Agrégation HTF + mapping non-repaint ===================
def aggregate(t, o, h, l, c, v, delta, bucket):
    """Agrège les barres 1h en buckets (4h ou 1D) + somme delta taker."""
    bt, bo, bh, bl, bc, bv, bd = [], [], [], [], [], [], []
    for i, ti in enumerate(t):
        k = ti // bucket
        if bt and k == (bt[-1] // bucket):
            bh[-1] = max(bh[-1], h[i]); bl[-1] = min(bl[-1], l[i])
            bc[-1] = c[i]; bv[-1] += v[i]; bd[-1] += delta[i]
        else:
            bt.append(ti); bo.append(o[i]); bh.append(h[i])
            bl.append(l[i]); bc.append(c[i]); bv.append(v[i]); bd.append(delta[i])
    return bt, bo, bh, bl, bc, bv, bd


class SymData:
    """Indicateurs d'un symbole : vues 1h confirmées (k-1) + vues close-bucket (k)."""

    def __init__(self, symbol):
        self.sym = symbol
        t, o, h, l, c, v, tb = load_klines(symbol)
        self.t, self.o, self.h, self.l, self.c = t, o, h, l, c
        n = len(t)
        self.n = n
        delta = [(2.0 * tb[i] - v[i]) * c[i] for i in range(n)]
        # CVD 1h (Alpha 1, chart H1)
        acc = 0.0
        cvd1 = []
        for d in delta:
            acc += d
            cvd1.append(acc)
        self.cvd1 = cvd1
        self.cvd1e = ema(cvd1, 21)
        # funding ffill
        fund = load_funding(symbol)
        f_rate = [0.0] * n
        fi, last_f = 0, 0.0
        for i in range(n):
            while fi < len(fund) and fund[fi][0] <= t[i]:
                last_f = fund[fi][1]
                fi += 1
            f_rate[i] = last_f
        self.f_rate = f_rate
        # agrégats H4 et D1
        b4 = aggregate(t, o, h, l, c, v, delta, B4)
        b1d = aggregate(t, o, h, l, c, v, delta, 86400000)
        self._build_h4(b4)
        self._build_d1(b1d)
        # mappage confirmé k-1 sur chaque barre 1h
        self.m = {}
        base4 = t[0] // B4
        base1d = t[0] // 86400000
        self.close_idx4 = [None] * n   # index bucket H4 de chaque barre 1h
        for i in range(n):
            self.close_idx4[i] = t[i] // B4 - base4
        for key, series in self.h4s.items():
            self.m[key] = [series[k - 1] if 0 <= k - 1 < len(series) else None
                           for k in self.close_idx4]
        for key, series in self.d1s.items():
            self.m[key] = [series[k - 1] if 0 <= k - 1 < len(series) else None
                           for k in [ti // 86400000 - base1d for ti in t]]
        self.base4 = base4
        self.base1d = base1d

    def _build_h4(self, b4):
        bt, bo, bh, bl, bc, bv, bd = b4
        self.b4 = b4
        h4s = {}
        h4s["c4"] = bc
        h4s["e4t"] = ema(bc, 50)          # EMA tendance 4h (A1/A4)
        h4s["e4z"] = ema(bc, 21)          # EMA zone 4h (A1/A3 défensive)
        h4s["adx4"] = wilder_adx(bh, bl, bc, 14)
        a14 = wilder_atr(bh, bl, bc, 14)
        h4s["atr4pct"] = [None if a14[i] is None else a14[i] / bc[i] * 100.0
                          for i in range(len(bc))]
        h4s["rsi4"] = rsi(bc, 14)         # A2
        h4s["st"] = supertrend(bh, bl, bc, 3.0, 10)   # A4
        ks, ds = stoch(bh, bl, bc, 14, 3, 3)          # A4
        h4s["stok"], h4s["stod"] = ks, ds
        # Bollinger width + moyenne (A3)
        ma20 = sma(bc, 20); sd20 = stdev(bc, 20)
        width = [None if ma20[i] is None else (4.0 * sd20[i]) / ma20[i]
                 for i in range(len(bc))]
        h4s["bbw"] = width
        h4s["bbwm"] = sma([x if x is not None else 0.0 for x in width], 30)
        # squeeze : largeur < 60 % de sa moyenne
        sqz = [False] * len(bc)
        for i in range(len(bc)):
            if width[i] is not None and h4s["bbwm"][i]:
                sqz[i] = width[i] < h4s["bbwm"][i] * 0.60
        h4s["sqz"] = sqz
        # âge de la dernière compression (barssince)
        age = [None] * len(bc)
        last = None
        for i in range(len(bc)):
            if sqz[i]:
                last = i
            age[i] = None if last is None else i - last
        h4s["sqzAge"] = age
        # canal Donchian 20 (incluant la barre courante) + canal précédent [1]
        h4s["donHi"] = rolling_max(bh, 20)
        h4s["donLo"] = rolling_min(bl, 20)
        # volume + moyenne
        h4s["vol"] = bv
        h4s["volMa"] = sma(bv, 30)
        # CVD 4h (A2/A3/A4)
        acc = 0.0
        cvd4 = []
        for d in bd:
            acc += d
            cvd4.append(acc)
        h4s["cvd4"] = cvd4
        h4s["cvd4e"] = ema(cvd4, 14)
        # extrêmes de purge A2
        h4s["purgeLo"] = rolling_min(bl, 8)
        h4s["purgeHi"] = rolling_max(bh, 8)
        # swing A4
        h4s["swLo"] = rolling_min(bl, 6)
        h4s["swHi"] = rolling_max(bh, 6)
        self.h4s = h4s

    def _build_d1(self, b1d):
        bt, bo, bh, bl, bc, bv, bd = b1d
        self.d1s = {"c1": bc, "e1t": ema(bc, 50)}

    def bucket_close(self, i):
        """Valeur close-bucket k (utilisée uniquement aux closes 4h)."""
        k = self.close_idx4[i]
        return k

    def get(self, key, i):
        return self.m[key][i]

    def get_k(self, key, k):
        s = self.h4s[key]
        return s[k] if 0 <= k < len(s) else None


@dataclass
class Trade:
    key: str
    side: int
    entry_time: int = 0
    exit_time: int = 0
    entry: float = 0.0
    exit_avg: float = 0.0
    qty0: float = 0.0
    risk_usd: float = 0.0
    stop0: float = 0.0
    pnl: float = 0.0
    legs: list = field(default_factory=list)
    reason: str = ""


@dataclass
class Pos:
    key: str
    alpha: str
    sym: str
    side: int
    qty: float
    entry: float
    stop0: float
    risk_usd: float
    tp1_px: float = 0.0
    tp2_px: float = 0.0
    qty0: float = 0.0
    tp1_done: bool = False
    tp2_done: bool = False
    q_close: dict = field(default=None)
    cur: Trade = field(default=None)


# ============================ Signaux par alpha ==============================
# Plage de distance au stop (%) par alpha (inputs des .ks)
STOP_RANGE = {"A1": (0.6, 3.0), "A2": (0.6, 4.0), "A3": (0.8, 5.0), "A4": (0.6, 3.0)}
FUND_MAX = 0.0005          # funding trop chargé contre l'entrée (0,05 %)
FUND_MIN = 0.0002          # financement extrême min (0,02 %) — seuil ORIGINAL d'A2 : de vraies
                           # cascades uniquement (inexistantes sur la fenêtre 2026, flux neutre)
FUND_CAP = 0.004           # anomalie exclue (A2)
ATR_STOP_FAC = 0.7         # stop >= 0,7 × ATR% 4h : normalisation volatilité multi-actifs


def signal_A1(sd, i):
    """Signature H1 (chart 1h) : régime 4h+D1+ADX, repli EMA21 4h, CVD 1h qui
    croise, bougie d'appui, funding sous contrôle. Stop : swing 24 barres 1h."""
    c4, e4t, e4z = sd.m["c4"][i], sd.m["e4t"][i], sd.m["e4z"][i]
    a4x, c1, e1t = sd.m["adx4"][i], sd.m["c1"][i], sd.m["e1t"][i]
    if None in (c4, e4t, e4z, a4x, c1, e1t) or i < 25:
        return None
    fr = sd.f_rate[i]
    cvd, ce = sd.cvd1[i], sd.cvd1e[i]
    cvd_u = cvd > ce and sd.cvd1[i - 1] <= sd.cvd1e[i - 1]
    cvd_d = cvd < ce and sd.cvd1[i - 1] >= sd.cvd1e[i - 1]
    bull, bear = sd.c[i] > sd.o[i], sd.c[i] < sd.o[i]
    zl, zs = sd.l[i] <= e4z, sd.h[i] >= e4z
    rg_l = c4 > e4t and c1 > e1t and a4x > 18.0
    rg_s = c4 < e4t and c1 < e1t and a4x > 18.0
    sw_lo = min(sd.l[max(0, i - 24 + 1):i + 1])
    sw_hi = max(sd.h[max(0, i - 24 + 1):i + 1])
    if rg_l and zl and cvd_u and bull and fr < FUND_MAX:
        return (1, sw_lo * (1 - CFG["stopBufPct"] / 100))
    if rg_s and zs and cvd_d and bear and fr > -FUND_MAX:
        return (-1, sw_hi * (1 + CFG["stopBufPct"] / 100))
    return None


def signal_A2(sd, i, k):
    """Cascade & Financement (H4, flux liquidations indisponible -> financement
    extrême + RSI capitulation + CVD qui absorbe + bougie d'appui).
    Stop : au-delà de l'extrême de purge 8 barres 4h."""
    c1, e1t = sd.m["c1"][i], sd.m["e1t"][i]
    rsi_k, cvd, ce = sd.get_k("rsi4", k), sd.get_k("cvd4", k), sd.get_k("cvd4e", k)
    cvd_p, ce_p = sd.get_k("cvd4", k - 1), sd.get_k("cvd4e", k - 1)
    p_lo, p_hi = sd.get_k("purgeLo", k), sd.get_k("purgeHi", k)
    if None in (c1, e1t, rsi_k, cvd, ce, cvd_p, ce_p, p_lo, p_hi):
        return None
    fr = sd.f_rate[i]
    fundExtNeg = -FUND_CAP <= fr <= -FUND_MIN
    fundExtPos = FUND_MIN <= fr <= FUND_CAP
    cvd_up = cvd_p <= ce_p and cvd > ce
    cvd_dn = cvd_p >= ce_p and cvd < ce
    bull, bear = sd.c[i] > sd.o[i], sd.c[i] < sd.o[i]
    if sd.c[i] > c1 and fundExtNeg and rsi_k < 32 and cvd_up and bull and fr < FUND_MAX:
        return (1, p_lo * (1 - CFG["stopBufPct"] / 100))
    if sd.c[i] < c1 and fundExtPos and rsi_k > 68 and cvd_dn and bear and fr > -FUND_MAX:
        return (-1, p_hi * (1 + CFG["stopBufPct"] / 100))
    return None


def signal_A3(sd, i, k):
    """Éruption Volatilité (H4) : squeeze BB récent + cassure du canal Donchian
    20 (clôture au-dessus du canal précédent) + volume 1,5x + CVD + régime D1
    + ADX. Stop : de l'autre côté du canal."""
    donHi_p, donLo = sd.get_k("donHi", k - 1), sd.get_k("donLo", k)
    donHi, donLo_p = sd.get_k("donHi", k), sd.get_k("donLo", k - 1)
    bw, bwm, age = sd.get_k("bbw", k), sd.get_k("bbwm", k), sd.get_k("sqzAge", k)
    vol, volma = sd.get_k("vol", k), sd.get_k("volMa", k)
    cvd, ce, adx = sd.get_k("cvd4", k), sd.get_k("cvd4e", k), sd.get_k("adx4", k)
    c1, e1t = sd.m["c1"][i], sd.m["e1t"][i]
    if None in (donHi_p, donLo, donHi, donLo_p, bw, bwm, age, vol, volma,
                cvd, ce, adx, c1, e1t) or volma == 0:
        return None
    fr = sd.f_rate[i]
    erupt_up = sd.c[i] > donHi_p
    erupt_dn = sd.c[i] < donLo_p
    sqz_recent = age <= 8
    vol_ok = vol > 1.5 * volma
    if erupt_up and sqz_recent and vol_ok and cvd > ce and sd.c[i] > c1 and adx > 15 \
            and fr < FUND_MAX:
        return (1, donLo * (1 - CFG["stopBufPct"] / 100))
    if erupt_dn and sqz_recent and vol_ok and cvd < ce and sd.c[i] < c1 and adx > 15 \
            and fr > -FUND_MAX:
        return (-1, donHi * (1 + CFG["stopBufPct"] / 100))
    return None


def signal_A4(sd, i, k):
    """Confluence Multi-Périodes (H4) : régime D1+4h+ADX, SuperTrend, repli
    EMA21 4h, stochastique qui sort de survente/surachat, CVD, funding.
    Stop : sous le swing 6 barres 4h."""
    c4, e4t, e4z = sd.get_k("c4", k), sd.get_k("e4t", k), sd.get_k("e4z", k)
    adx, st_k = sd.get_k("adx4", k), sd.get_k("st", k)
    kk, dd = sd.get_k("stok", k), sd.get_k("stod", k)
    kk_p, dd_p = sd.get_k("stok", k - 1), sd.get_k("stod", k - 1)
    sw_lo, sw_hi = sd.get_k("swLo", k), sd.get_k("swHi", k)
    cvd, ce = sd.get_k("cvd4", k), sd.get_k("cvd4e", k)
    c1, e1t = sd.m["c1"][i], sd.m["e1t"][i]
    if None in (c4, e4t, e4z, adx, st_k, kk, dd, kk_p, dd_p, sw_lo, sw_hi,
                cvd, ce, c1, e1t):
        return None
    fr = sd.f_rate[i]
    low_b4, high_b4 = sd.b4[3][k], sd.b4[2][k]
    turn_up = kk_p <= dd_p and kk > dd and dd_p < 30
    turn_dn = kk_p >= dd_p and kk < dd and dd_p > 70
    if c4 > e4t and c1 > e1t and adx > 18 and st_k == 1 and low_b4 <= e4z \
            and turn_up and cvd > ce and fr < FUND_MAX:
        return (1, sw_lo * (1 - CFG["stopBufPct"] / 100))
    if c4 < e4t and c1 < e1t and adx > 18 and st_k == -1 and high_b4 >= e4z \
            and turn_dn and cvd < ce and fr > -FUND_MAX:
        return (-1, sw_hi * (1 + CFG["stopBufPct"] / 100))
    return None


SIGNALS = {"A2": signal_A2, "A3": signal_A3, "A4": signal_A4}
H1_SIGNALS = {"A1": signal_A1}
H1_ALPHAS = ["A1"]          # évalués à chaque barre 1h (extensible : v5 ajoute A5)
H4_ALPHAS = ["A2", "A3", "A4"]  # évalués aux closes 4h (extensible : v5 ajoute A6)
ALPHA_SCOPE = {}            # alpha -> liste de symboles autorisés (vide = tous)
CHOP_ADX_MIN = 15.0         # garde anti-chop : alts bloquées si ADX D1 BTC < seuil
CHOP_DISP_FAC = 1.0         # + déplacement BTC vs EMA50 D1 >= fac x ATR% D1


def build_entry(sig, key, alpha, sym, eq, i, SD, positions, q_entries):
    """Sizing x501 : risque fixe (%) plafonné par le budget de risque global
    (riskCapPct de l'équité) et par le levier effectif max."""
    side, stop = sig
    sd = SD[sym]
    px = sd.c[i]
    dist = abs(px - stop)
    if dist <= 0:
        return None
    dist_pct = dist / px * 100
    lo, hi = STOP_RANGE[alpha]
    if not (lo <= dist_pct <= hi):
        return None
    # normalisation volatilité : le stop doit être hors du bruit ATR 4h de l'actif
    atrpct = sd.m["atr4pct"][i]
    if atrpct is not None and dist_pct < ATR_STOP_FAC * atrpct:
        return None
    cap_usd = eq * CFG["riskCapPct"] / 100
    engaged = sum(p.risk_usd for p in positions.values())
    budget = cap_usd - engaged
    risk_usd = min(eq * CFG["riskPct"] / 100, budget)
    if risk_usd <= 0:
        return None
    qty = min(risk_usd / dist, eq * CFG["maxEffLev"] / px)
    if qty * px < CFG["minNotional"]:
        return None
    if engaged + qty * dist > cap_usd:
        return None
    return dict(side=side, qty=qty, stop=stop, alpha=alpha, sym=sym)


def run_portfolio(warmup_days=60):
    """Backtest portefeuille deep : flux échelonnés depuis le listing de chaque
    actif (politique docs/37), un compte, marge isolée par position."""
    SD = {s: SymData(s) for s in SYMS}
    # grille globale = timeline BTC (le listing le plus ancien du pool) ;
    # chaque symbole est résolu par bisect : index local du ts global, None
    # avant listing. Zéro assertion d'alignement (départs échelonnés).
    def G2L(sd, ts):
        j = bisect.bisect_left(sd.t, ts)
        return j if j < sd.n and sd.t[j] == ts else None
    t = SD[SYMS[0]].t
    n = len(t)

    # warmup PAR ACTIF : 60 j + 24 barres après SON premier bar (EMA50 D1 fiable)
    start_local = {}
    for s in SYMS:
        sd = SD[s]
        day0 = sd.t[0] // 86400000
        j = next(k for k in range(sd.n) if (sd.t[k] // 86400000) - day0 >= warmup_days)
        start_local[s] = min(j + 24, sd.n - 1)
    start_i = start_local[SYMS[0]]   # BTC local == global (grille = BTC)

    cash = CFG["initialCapital"]
    positions: dict[str, Pos] = {}
    q_entries: dict[str, dict] = {}
    eq_peak = cash
    halted = False
    day_anchor_t = day_anchor_eq = None
    week_anchor_t = week_anchor_eq = None
    blocked_day = blocked_week = 0
    total_fees = total_funding = 0.0
    trades: list[Trade] = []
    eq_series = []
    liq_hits = 0
    last_px = {s: None for s in SYMS}

    def unrealized(ts):
        u = 0.0
        for p in positions.values():
            sd = SD[p.sym]
            li = G2L(sd, ts)
            px = sd.c[li] if li is not None else last_px[p.sym]
            if px is not None:
                u += p.qty * (px - p.entry) * p.side
        return u

    def equity(ts):
        return cash + unrealized(ts)

    def engaged_risk():
        return sum(p.risk_usd for p in positions.values())

    def close_all_pos(p, px_fill, when, reason, fee_rate, i):
        nonlocal cash, total_fees
        notional = p.qty * px_fill
        fee = notional * fee_rate
        total_fees += fee
        pnl_leg = (px_fill - p.entry) * p.qty * p.side - fee
        cash += pnl_leg
        cur = p.cur
        if cur is not None:
            cur.legs.append((when, px_fill, p.qty, reason))
            cur.pnl += pnl_leg
            cur.reason += reason + ";"
        p.qty = 0.0

    def finalize_trade(p, i):
        cur = p.cur
        if cur is None:
            return
        cur.exit_time = cur.legs[-1][0] if cur.legs else t[i]
        qsum = sum(q for _, _, q, _ in cur.legs)
        cur.exit_avg = (sum(px * q for _, px, q, _ in cur.legs) / qsum) if qsum else cur.entry
        trades.append(cur)
        p.cur = None

    for i in range(n):
        ti = t[i]
        # ---------- 1. funding ----------
        if ti % (8 * 3600 * 1000) == 0:
            for p in positions.values():
                sd = SD[p.sym]
                li = G2L(sd, ti)
                if li is None:
                    continue
                pay = p.qty * sd.o[li] * sd.f_rate[li] * p.side
                cash -= pay
                total_funding -= pay
                if p.cur is not None:
                    p.cur.pnl -= pay

        # ---------- 2. exits protecteurs (brackets) ----------
        for key, p in list(positions.items()):
            if p.qty <= 0:
                continue
            sd = SD[p.sym]
            li = G2L(sd, ti)
            if li is None:
                continue
            hi, lo, op = sd.h[li], sd.l[li], sd.o[li]
            side = p.side
            stop_px = p.cur_stop
            stop_touch = lo <= stop_px if side == 1 else hi >= stop_px
            tp1_touch = (not p.tp1_done) and (hi >= p.tp1_px if side == 1 else lo <= p.tp1_px)
            tp2_touch = (not p.tp2_done) and (hi >= p.tp2_px if side == 1 else lo <= p.tp2_px)
            if stop_touch:
                fill = min(op, stop_px) * (1 - CFG["slip"]) if side == 1 else max(op, stop_px) * (1 + CFG["slip"])
                reason = "stop" if not (p.tp1_done and p.tp2_done) else "trail"
                close_all_pos(p, fill, ti, reason, CFG["taker"], i)
                finalize_trade(p, i)
                del positions[key]
            else:
                if tp1_touch:
                    fill = max(op, p.tp1_px) if side == 1 else min(op, p.tp1_px)
                    q = min(p.qty0 * 0.50, p.qty)
                    fee = q * fill * CFG["maker"]
                    total_fees += fee
                    pnl_leg = (fill - p.entry) * q * side - fee
                    cash += pnl_leg
                    p.qty -= q
                    if p.cur is not None:
                        p.cur.legs.append((ti, fill, q, "tp1"))
                        p.cur.pnl += pnl_leg
                    p.tp1_done = True
                if tp2_touch and p.qty > 0:
                    fill = max(op, p.tp2_px) if side == 1 else min(op, p.tp2_px)
                    q = min(p.qty0 * 0.25, p.qty)
                    fee = q * fill * CFG["maker"]
                    total_fees += fee
                    pnl_leg = (fill - p.entry) * q * side - fee
                    cash += pnl_leg
                    p.qty -= q
                    if p.cur is not None:
                        p.cur.legs.append((ti, fill, q, "tp2"))
                        p.cur.pnl += pnl_leg
                    p.tp2_done = True
                if p.qty <= 1e-12:
                    finalize_trade(p, i)
                    del positions[key]

        # ---------- 3. exits signal (au close préc.) ----------
        for key, p in list(positions.items()):
            if p.qty > 0 and p.q_close is not None:
                sd = SD[p.sym]
                li = G2L(sd, ti)
                if li is None:
                    continue
                fill = sd.o[li] * (1 - CFG["slip"]) if p.side == 1 else sd.o[li] * (1 + CFG["slip"])
                close_all_pos(p, fill, ti, p.q_close["reason"], CFG["taker"], i)
                finalize_trade(p, i)
                p.q_close = None
                del positions[key]

        # ---------- 4. entries au marché (au close préc.) ----------
        for key, q in list(q_entries.items()):
            if key in positions:
                del q_entries[key]
                continue
            sd = SD[q["sym"]]
            li = G2L(sd, ti)
            if li is None:
                del q_entries[key]
                continue
            s = q["side"]
            fill = sd.o[li] * (1 + CFG["slip"]) if s == 1 else sd.o[li] * (1 - CFG["slip"])
            qty = q["qty"]
            fee = qty * fill * CFG["taker"]
            total_fees += fee
            cash -= fee
            p = Pos(key=key, alpha=q["alpha"], sym=q["sym"], side=s, qty=qty,
                    entry=fill, stop0=q["stop"], risk_usd=qty * abs(fill - q["stop"]))
            p.qty0 = qty
            p.cur_stop = q["stop"]
            risk_px = abs(fill - q["stop"])
            p.tp1_px = fill + s * 1.5 * risk_px
            p.tp2_px = fill + s * 2.5 * risk_px
            cur = Trade(key=key, side=s, entry_time=ti, entry=fill, qty0=qty,
                        risk_usd=p.risk_usd, stop0=q["stop"])
            cur.pnl = -fee
            p.cur = cur
            positions[key] = p
            del q_entries[key]

        # ---------- 5. contrôle liquidation (marge isolée par position) ----------
        for key, p in list(positions.items()):
            if p.qty <= 0:
                continue
            sd = SD[p.sym]
            li = G2L(sd, ti)
            if li is None:
                continue
            notional = p.qty * sd.c[li]
            margin = notional / CFG["nomLev"]
            if p.side == 1:
                pliq = p.entry - (margin - CFG["mmr"] * notional) / p.qty
                if sd.l[li] <= pliq:
                    liq_hits += 1
                    fill = min(sd.o[li], pliq)
                    close_all_pos(p, fill, ti, "liquidation", CFG["taker"], i)
                    finalize_trade(p, i)
                    del positions[key]
            else:
                pliq = p.entry + (margin - CFG["mmr"] * notional) / p.qty
                if sd.h[li] >= pliq:
                    liq_hits += 1
                    fill = max(sd.o[li], pliq)
                    close_all_pos(p, fill, ti, "liquidation", CFG["taker"], i)
                    finalize_trade(p, i)
                    del positions[key]

        # ---------- marquage équité ----------
        eq = equity(ti)
        for s2 in SYMS:
            l2 = G2L(SD[s2], ti)
            if l2 is not None:
                last_px[s2] = SD[s2].c[l2]
        eq_series.append((ti, eq))

        # ---------- 6. script au close ----------
        eq_peak = max(eq_peak, eq)
        dd = (1 - eq / eq_peak) * 100 if eq_peak > 0 else 0.0
        if CFG["killDD"] is not None and dd >= CFG["killDD"]:
            halted = True
        if day_anchor_t is None:
            day_anchor_t, day_anchor_eq = ti, eq
            week_anchor_t, week_anchor_eq = ti, eq
        if ti - day_anchor_t >= 86400000:
            day_anchor_t, day_anchor_eq = ti, eq
        day_loss = max(0.0, (1 - eq / day_anchor_eq) * 100) if day_anchor_eq > 0 else 0.0
        if ti - week_anchor_t >= 604800000:
            week_anchor_t, week_anchor_eq = ti, eq
        week_loss = max(0.0, (1 - eq / week_anchor_eq) * 100) if week_anchor_eq > 0 else 0.0
        breakers_ok = (not halted) and day_loss < CFG["dailyStop"] and week_loss < CFG["weeklyStop"]
        if not breakers_ok:
            if day_loss >= CFG["dailyStop"]:
                blocked_day += 1
            elif week_loss >= CFG["weeklyStop"]:
                blocked_week += 1

        is_h4_close = (ti % B4) == B4 - B1   # dernière barre 1h du bucket 4h

        # --- gestion des positions ouvertes : ré-armement brackets + sorties défensives
        for key, p in positions.items():
            if p.qty <= 0:
                continue
            sd = SD[p.sym]
            li = G2L(sd, ti)
            if li is None:
                continue
            i = li          # ombre locale : tout le bloc parle en index du symbole
            stop_now = p.entry if p.tp1_done else p.stop0
            if p.tp2_done:
                # trail : A1/A5 = 24 barres 1h ; A2/A3/A4/A6 = 5 barres 4h confirmées (k-4..k)
                if p.alpha in ("A1", "A5"):
                    w = 24
                    lo_w = min(sd.l[max(0, i - w + 1):i + 1])
                    hi_w = max(sd.h[max(0, i - w + 1):i + 1])
                elif is_h4_close:
                    k = sd.bucket_close(i)
                    lows = [sd.b4[3][kk] for kk in range(max(0, k - 4), k + 1)]
                    highs = [sd.b4[2][kk] for kk in range(max(0, k - 4), k + 1)]
                    lo_w, hi_w = min(lows), max(highs)
                else:
                    lo_w, hi_w = None, None
                if lo_w is not None:
                    if p.side == 1:
                        stop_now = max(stop_now, lo_w * (1 - CFG["trailBufPct"] / 100))
                    else:
                        stop_now = min(stop_now, hi_w * (1 + CFG["trailBufPct"] / 100))
            p.cur_stop = stop_now
            # sorties défensives : A1 chaque barre 1h ; A2/A3/A4 au close 4h seulement
            defensive = None
            c1, e1 = sd.m["c1"][i], sd.m["e1t"][i]
            if p.alpha in ("A1", "A5") and c1 is not None and e1 is not None:
                if p.alpha == "A1":
                    if (p.side == 1 and c1 < e1) or (p.side == -1 and c1 > e1):
                        defensive = "trendflip"
                else:  # A5 : sortie défensive zone EMA21 H1, bruit 0,5x ATR 1h filtré
                    e5z = getattr(sd, "e1z", None)
                    a1 = getattr(sd, "atr1", None)
                    if e5z is not None and e5z[i] is not None:
                        noise = (0.5 * a1[i]) if (a1 is not None and a1[i]) else 0.0
                        if (p.side == 1 and sd.c[i] < e5z[i] - noise) or \
                           (p.side == -1 and sd.c[i] > e5z[i] + noise):
                            defensive = "zoneH1"
            elif is_h4_close:
                k = sd.bucket_close(i)
                if p.alpha == "A4":
                    st_k = sd.get_k("st", k)
                    if (p.side == 1 and st_k == -1) or (p.side == -1 and st_k == 1):
                        defensive = "flipST"
                elif p.alpha == "A3":
                    if (p.side == 1 and sd.c[i] < sd.get_k("e4z", k)) or \
                       (p.side == -1 and sd.c[i] > sd.get_k("e4z", k)):
                        defensive = "avortee"
                elif p.alpha == "A2" and c1 is not None and e1 is not None:
                    if (p.side == 1 and c1 < e1) or (p.side == -1 and c1 > e1):
                        defensive = "trendflip"
                elif p.alpha == "A6":
                    e4z_k = sd.get_k("e4z", k)
                    if e4z_k is not None:
                        if (p.side == 1 and sd.c[i] < e4z_k) or \
                           (p.side == -1 and sd.c[i] > e4z_k):
                            defensive = "zone_perdue"
            if defensive is not None and p.q_close is None:
                p.q_close = dict(reason=defensive)

        # --- détection de signaux (flux plats uniquement)
        btc0 = SD["BTCUSDT"]
        btc_reg_up = (btc0.m["c1"][i] is not None and btc0.m["e1t"][i] is not None
                      and btc0.m["c1"][i] > btc0.m["e1t"][i])
        btc_adx1 = btc0.m["adx1"][i] if "adx1" in btc0.m else None
        btc_directionnel = btc_adx1 is None or btc_adx1 > CHOP_ADX_MIN
        if btc_directionnel and btc_adx1 is not None and btc0.m["c1"][i] is not None \
                and btc0.m["e1t"][i] is not None and "atr1dpct" in btc0.m \
                and btc0.m["atr1dpct"][i] is not None:
            # v5.2 : BTC doit être sorti de sa moyenne D1 d'au moins fac x ATR% D1
            disp = abs(btc0.m["c1"][i] / btc0.m["e1t"][i] - 1) * 100
            if disp < CHOP_DISP_FAC * btc0.m["atr1dpct"][i]:
                btc_directionnel = False
        if breakers_ok:
            for sym in SYMS:
                sd = SD[sym]
                li = G2L(sd, ti)
                if li is None or li < start_local[sym]:
                    continue      # actif pas encore listé / en warmup
                i = li            # ombre locale : signaux en index du symbole
                for alpha in H1_ALPHAS:
                    if sym not in ALPHA_SCOPE.get(alpha, SYMS):
                        continue
                    key = f"{alpha}:{sym}"
                    if key not in positions and key not in q_entries:
                        sig = H1_SIGNALS[alpha](sd, i)
                        if sig and sym != "BTCUSDT":
                            # filtre beta + garde anti-chop : un alt ne s'ouvre jamais
                            # contre le régime D1 de BTC ni en marché sans direction
                            ok = btc_reg_up if sig[0] == 1 else (not btc_reg_up)
                            if not ok or not btc_directionnel:
                                sig = None
                        if sig:
                            qe = build_entry(sig, key, alpha, sym, eq, i, SD, positions, q_entries)
                            if qe:
                                q_entries[key] = qe
                if is_h4_close:
                    k = sd.bucket_close(i)
                    for alpha in H4_ALPHAS:
                        if sym not in ALPHA_SCOPE.get(alpha, SYMS):
                            continue
                        key = f"{alpha}:{sym}"
                        if key in positions or key in q_entries:
                            continue
                        sig = SIGNALS[alpha](sd, i, k)
                        if sig and sym != "BTCUSDT":
                            ok = btc_reg_up if sig[0] == 1 else (not btc_reg_up)
                            if not ok:
                                sig = None
                        if sig:
                            qe = build_entry(sig, key, alpha, sym, eq, i, SD, positions, q_entries)
                            if qe:
                                q_entries[key] = qe

        # coupe-circuit -25 % (mode plan seulement)
        if halted:
            for key, p in list(positions.items()):
                if p.qty > 0 and p.q_close is None:
                    p.q_close = dict(reason="kill25")

    # clôture finale (chaque flux à la clôture de SA dernière barre)
    for key, p in list(positions.items()):
        sd = SD[p.sym]
        fill = sd.c[-1] * (1 - CFG["slip"]) if p.side == 1 else sd.c[-1] * (1 + CFG["slip"])
        close_all_pos(p, fill, max(t[-1], sd.t[-1]), "fin", CFG["taker"], n - 1)
        finalize_trade(p, n - 1)
        del positions[key]

    return dict(trades=trades, eq_series=eq_series, total_fees=total_fees,
                total_funding=total_funding, blocked_day=blocked_day,
                blocked_week=blocked_week, halted=halted, liq_hits=liq_hits,
                start_i=start_i, n=n, t=t)


# ================================ Statistiques ===============================
def max_dd_of(eq_series):
    peak = eq_series[0][1]
    md = 0.0
    for _, e in eq_series:
        peak = max(peak, e)
        md = max(md, (1 - e / peak) * 100)
    return md


def stats_block(trades, eq_series, cap0):
    rs = [tr.pnl / tr.risk_usd for tr in trades if tr.risk_usd > 0]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gp, gl = sum(wins), abs(sum(losses))
    return dict(
        n=len(trades),
        wr=100.0 * len(wins) / len(rs) if rs else 0.0,
        pf=gp / gl if gl > 0 else float("inf"),
        avg_r=sum(rs) / len(rs) if rs else 0.0,
        med_r=sorted(rs)[len(rs) // 2] if rs else 0.0,
        best=max(rs) if rs else 0.0,
        worst=min(rs) if rs else 0.0,
        max_dd=max_dd_of(eq_series),
        final=eq_series[-1][1],
        ret=(eq_series[-1][1] / cap0 - 1) * 100,
        longs=sum(1 for tr in trades if tr.side == 1),
        shorts=sum(1 for tr in trades if tr.side == -1),
    )


def utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    res = run_portfolio()
    trades = res["trades"]
    eqs = res["eq_series"]
    t0, tN = eqs[0][0], eqs[-1][0]
    t_start = res["t"][res["start_i"]]           # début effectif de trading (après warmup)
    months = (tN - t_start) / 86400000 / 30.4375  # fenêtre de trading seule

    glob = stats_block(trades, eqs, CFG["initialCapital"])
    glob["fees"] = res["total_fees"]
    glob["funding"] = res["total_funding"]
    glob["blocked_day"] = res["blocked_day"]
    glob["blocked_week"] = res["blocked_week"]
    glob["liq"] = res["liq_hits"]
    glob["cadence"] = len(trades) / months

    # par alpha
    by_alpha = {}
    for a in ALPHAS:
        tr_a = [tr for tr in trades if tr.key.startswith(a + ":")]
        eq_stub = [(0, CFG["initialCapital"]), (1, CFG["initialCapital"])]
        st = stats_block(tr_a, eq_stub, CFG["initialCapital"]) if tr_a else dict(
            n=0, wr=0.0, pf=0.0, avg_r=0.0, med_r=0.0, best=0.0, worst=0.0,
            max_dd=0.0, final=CFG["initialCapital"], ret=0.0, longs=0, shorts=0)
        st["cadence"] = len(tr_a) / months
        # maxDD propre à l'alpha : courbe d'équité marginale reconstruite
        order = sorted(tr_a, key=lambda x: x.exit_time)
        eq_a, peak, md = CFG["initialCapital"], CFG["initialCapital"], 0.0
        cap = CFG["initialCapital"]
        for tr in order:
            cap += tr.pnl
            peak = max(peak, cap)
            md = max(md, (1 - cap / peak) * 100)
        st["max_dd_marginal"] = md
        st["final_marginal"] = cap
        st["ret_marginal"] = (cap / CFG["initialCapital"] - 1) * 100
        by_alpha[a] = st

    # rendements mensuels réels (mois calendaires UTC)
    monthly = {}
    for tr in trades:
        m = dt.datetime.fromtimestamp(tr.entry_time / 1000, dt.timezone.utc).strftime("%Y-%m")
        monthly.setdefault(m, []).append(tr.pnl / tr.risk_usd if tr.risk_usd > 0 else 0.0)
    monthly_rows = []
    for m in sorted(monthly):
        rs_m = monthly[m]
        monthly_rows.append(dict(mois=m, trades=len(rs_m),
                                 r_moyen=sum(rs_m) / len(rs_m),
                                 r_somme=sum(rs_m)))

    # équité de fin de mois calendaire
    eq_monthly = []
    for m in sorted({dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).strftime("%Y-%m")
                     for x, _ in eqs}):
        vals = [(ts, e) for ts, e in eqs
                if dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).strftime("%Y-%m") == m]
        eq_monthly.append((m, vals[-1][1]))

    # ---- rapport console (français)
    print("=" * 74)
    print("OPÉRATION x501 — v30 DEEP : PORTEFEUILLE MULTI-ALPHA DEPUIS LE LISTING DE CHAQUE ACTIF")
    print("Source : bn_kline_1h_deep (Binance fapi, 2019-09 ->) + bn_funding_deep | taker réel 4,5 bps")
    print(f"Période : {utc(t0)} -> {utc(tN)}  ({months:.1f} mois)  |  capital initial 100 $")
    print(f"Flux : {len(SYMS)} actifs × {len(ALPHAS)} alphas | risque {CFG['riskPct']} %/trade, "
          f"plafond engagé {CFG['riskCapPct']} % | kill -25 % : {'ON' if CFG['killDD'] else 'OFF (mesure)'}")
    print("=" * 74)
    print(f"\n--- PORTEFEUILLE ---")
    print(f"trades={glob['n']} ({glob['longs']}L/{glob['shorts']}S)  cadence={glob['cadence']:.1f}/mois")
    print(f"WR={glob['wr']:.1f}%  PF={glob['pf']:.2f}  E[R]={glob['avg_r']:+.3f} R  "
          f"medR={glob['med_r']:+.2f}  best={glob['best']:+.1f}  worst={glob['worst']:+.1f}")
    print(f"équité finale={glob['final']:.2f}$  retour={glob['ret']:+.1f}%  maxDD brut={glob['max_dd']:.1f}%")
    print(f"frais={glob['fees']:.2f}$  funding={glob['funding']:.3f}$  "
          f"blocages jour={glob['blocked_day']} semaine={glob['blocked_week']}  liquidations={glob['liq']}")
    print("\n--- PAR ALPHA ---")
    for a in ALPHAS:
        st = by_alpha[a]
        print(f"{a}: n={st['n']:3d} ({st['cadence']:4.1f}/mois)  WR={st['wr']:5.1f}%  "
              f"PF={st['pf']:5.2f}  E[R]={st['avg_r']:+.3f}  maxDDm={st['max_dd_marginal']:5.1f}%  "
              f"finalm={st['final_marginal']:8.2f}$ ({st['ret_marginal']:+.0f}%)")
    print("\n--- PAR MOIS CALENDAIRE (R moyens des trades du mois) ---")
    for row in monthly_rows:
        print(f"  {row['mois']}: n={row['trades']:3d}  R moyen={row['r_moyen']:+.3f}  "
              f"R somme={row['r_somme']:+.2f}")
    print("\n--- ÉQUITÉ FIN DE MOIS ---")
    for m, e in eq_monthly:
        print(f"  {m}: {e:8.2f}$  ({(e / CFG['initialCapital'] - 1) * 100:+.1f}%)")

    # ---- exports
    with open(os.path.join(OUT, "trades_deep_v30.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["flux", "entree_utc", "sortie_utc", "sens", "entree_px",
                    "sortie_px_moy", "risque_usd", "pnl_usd_net", "R", "sorties"])
        for tr in sorted(trades, key=lambda x: x.entry_time):
            r = tr.pnl / tr.risk_usd if tr.risk_usd > 0 else 0
            w.writerow([tr.key, utc(tr.entry_time), utc(tr.exit_time),
                        "long" if tr.side == 1 else "short",
                        f"{tr.entry:.2f}", f"{tr.exit_avg:.2f}",
                        f"{tr.risk_usd:.3f}", f"{tr.pnl:.4f}", f"{r:.3f}",
                        "|".join(f"{rr}:{px:.2f}x{q:.6f}" for _, px, q, rr in tr.legs)])
    with open(os.path.join(OUT, "engine_deep_v30.json"), "w") as f:
        json.dump(dict(glob=glob, by_alpha=by_alpha, par_symbole={s: stats_block(
                              [tr for tr in trades if tr.key.endswith(":" + s)],
                              [(0, CFG["initialCapital"]), (1, CFG["initialCapital"])],
                              CFG["initialCapital"])
                          for s in SYMS if any(tr.key.endswith(":" + s) for tr in trades)},
                       monthly=monthly_rows,
                       eq_monthly=[[m, e] for m, e in eq_monthly],
                       periode=[utc(t0), utc(tN), months],
                       cfg={k: v for k, v in CFG.items()}), f, indent=2, ensure_ascii=False)
    slim = dict(eq=[(ts, e) for ts, e in eqs],
                trades=[dict(key=tr.key, t_in=tr.entry_time, t_out=tr.exit_time,
                             side=tr.side, pnl=tr.pnl, risk=tr.risk_usd,
                             entry=tr.entry, legs=[list(lg) for lg in tr.legs],
                             R=tr.pnl / tr.risk_usd if tr.risk_usd > 0 else 0.0)
                        for tr in trades],
                periode=[t0, tN, months])
    with open(os.path.join(OUT, "pool_v30_deep.pkl"), "wb") as f:
        pickle.dump(slim, f)
    print(f"\nExports -> {OUT}/ (trades_deep_v30.csv, engine_deep_v30.json, pool_v30_deep.pkl)")
