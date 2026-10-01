#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OPÉRATION x501 — v8 DEEP v31 : harnais v8 (40 symboles, gates IS/OOS,
gate ATR) porté sur la base deep « depuis le début de l'actif » (docs/37).

PORTAGE FIDÈLE de x501_v8_scale.py par transformation contrôlée : moteur,
indicateurs (patch v5), règles figées (seuils IS/OOS n>=40/20, E[R]>=+0,10,
PF>=1,25 ; gate θ ∈ {p50..p80} calibré IS uniquement ; sorties V0-V3 figées),
checkpoints et séquence de décision sont INCHANGÉS bit à bit. Seule la donnée
change : klines Binance deep depuis le listing (2,02 M barres, 40 symboles,
BTC 2019-09-08 ->) + funding deep, lues dans om_v27.db (tables *_deep).

Source : OPÉRATION x501 — v8 : INDUSTRIALISATION DE L'EDGE ROBUSTE À L'ÉCHELLE.

Réponse directe au verdict v7 (P(x501) = 0 % avec l'edge +0,21 R à cadence
6,2/mois ; il faut edge x3,5 -> +0,75 R ET cadence x3) : v8 attaque les DEUX
leviers identifiés, avec la même discipline anti-surapprentissage (règles
figées AVANT mesure, sélection sur IS 60 %, confirmation sur OOS 40 %).

LEVIER CADENCE (déploiement) :
  - Univers étendu 16 -> 40 perps Binance USDT-M (36 mois, données réelles).
  - Flux robustes déployés : A3 (Éruption Volatilité, +0,25 R PF 1,96 sur 3 ans)
    et A4 (Confluence MTF, +0,49 R PF 2,04) sur TOUTES les paires — le verdict
    v4 « A4 dilué sur alts » est RETESTÉ honnêtement sur 38 alts x 36 mois ;
    A1 (Signature H1) reste premium BTC/ETH (n=26, +0,914 R certifié v7).
  - A2 (1 trade/3 ans) et A6 (E[R] ~ 0) exclus a priori : dilution pure.

LEVIER EDGE (qualité par trade, 2 leviers figés a priori) :
  L1 « Gate volatilité »  : v7 a montré 2026 (+0,48 R) >> 2024/25 (+0,09 R) ;
        hypothèse : le tape paie quand la volatilité BTC D1 est haute.
        Gate : BTC ATR% D1 >= θ, θ ∈ {p50, p60, p70, p80} de la distribution IS
        uniquement. Sélection : max E[R] IS avec n_IS >= 40 ; RETENU seulement
        si OOS valide (n >= 20, E[R] >= +0,10 R, PF >= 1,25, somme > 0).
  L2 « Échelle de sortie »: variantes figées a priori (aucun tuning fin) :
        V0 référence (TP1 +1,5R 50 % / TP2 +2,5R 25 % / trail 5x4h) ;
        V1 runner (TP2 +3,5R) ; V2 runner+ (TP2 +4,0R, trail 8x4h) ;
        V3 early (TP1 +1,0R). Décision sur le pool satellite IS (n grand),
        confirmation OOS requise (mêmes seuils). Sinon V0 conservé.

Exécution IDENTIQUE à la plateforme (harnais v7 inchangé) : stop d'abord,
taker 4,5 bps + slippage 2 bps, TPs maker, funding réel 8 h, marge isolée 10x,
brackets armés la bougie suivante, coupe-circuits jour/semaine en mode MESURE
(R-multiples invariants au sizing -> réutilisables par le Monte-Carlo).

Sortie : scripts/x501_v8_results/ (research_v8_deep.json, pool_v8_deep.pkl, trades_v8_deep.csv)
"""
import csv
import json
import os
import pickle
import sys
import datetime as dtm

sys.path.insert(0, "/home/z/my-project/scripts")
import x501_alpha_backtest as v4          # noqa: E402

# ================= PORTAGE DEEP v31 (docs/37) ================================
# Le chargement CSV 36 mois est remplacé par la lecture DB deep (klines 1h
# depuis le LISTING de chaque actif + funding Binance deep). Les INDICATEURS
# et le moteur (SymData patché v5, run_stream) sont inchangés bit à bit :
# seul le segment de données change. Funding ts en SECONDES -> ms ici.
import sqlite3
_DB_DEEP = "/home/z/my-project/scripts/x501_v21_results/om_v27.db"
_DBC = sqlite3.connect(_DB_DEEP, timeout=120)


def load_klines_deep(symbol):
    rows = _DBC.execute(
        "SELECT ts, open, high, low, close, volume, taker_buy "
        "FROM bn_kline_1h_deep WHERE symbol=? ORDER BY ts", (symbol,)).fetchall()
    t = [r[0] for r in rows]
    o = [r[1] for r in rows]
    h = [r[2] for r in rows]
    lo = [r[3] for r in rows]
    c = [r[4] for r in rows]
    v = [r[5] for r in rows]
    tb = [r[6] for r in rows]
    return t, o, h, lo, c, v, tb


def load_funding_deep(symbol):
    rows = _DBC.execute(
        "SELECT ts * 1000, rate FROM bn_funding_deep WHERE symbol=? ORDER BY ts",
        (symbol,)).fetchall()
    return [(int(r[0]), float(r[1])) for r in rows]


v4.load_klines = load_klines_deep
v4.load_funding = load_funding_deep
print("Chargement DEEP depuis", _DB_DEEP, flush=True)

import x501_engine_v5 as v5               # noqa: E402  (patch SymData : e1z, atr1, vol1ma, adx1, atr1dpct)

OUT = "/home/z/my-project/scripts/x501_v8_results_deep_v31"
os.makedirs(OUT, exist_ok=True)

SYMS_V8 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
           "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT", "DOTUSDT",
           "LTCUSDT", "TRXUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
           "ATOMUSDT", "ETCUSDT", "BCHUSDT", "FILUSDT", "UNIUSDT",
           "AAVEUSDT", "HBARUSDT", "VETUSDT", "ICPUSDT", "FETUSDT",
           "INJUSDT", "LDOUSDT", "GALAUSDT", "IMXUSDT", "STXUSDT",
           "WLDUSDT", "SEIUSDT", "SUIUSDT", "TIAUSDT", "1000PEPEUSDT",
           "1000SHIBUSDT", "1000FLOKIUSDT", "JUPUSDT", "ORDIUSDT"]
PREM = {"BTCUSDT", "ETHUSDT"}
B1H = 3600 * 1000
B4 = 4 * B1H
CFG = v4.CFG
CHOP_ADX_MIN, CHOP_DISP_FAC = v4.CHOP_ADX_MIN, v4.CHOP_DISP_FAC
FUND_MAX = v4.FUND_MAX

EXIT_V0 = dict(tp1_mult=1.5, tp2_mult=2.5, tp1_frac=0.50, tp2_frac=0.25, trail4=5)
EXIT_VARIANTS = {
    "V0": EXIT_V0,
    "V1": dict(tp1_mult=1.5, tp2_mult=3.5, tp1_frac=0.50, tp2_frac=0.25, trail4=5),
    "V2": dict(tp1_mult=1.5, tp2_mult=4.0, tp1_frac=0.50, tp2_frac=0.25, trail4=8),
    "V3": dict(tp1_mult=1.0, tp2_mult=2.5, tp1_frac=0.50, tp2_frac=0.25, trail4=5),
}
GATE_CANDIDATES = ("p50", "p60", "p70", "p80")   # figés a priori


def utc(ms):
    return dtm.datetime.fromtimestamp(ms / 1000, dtm.timezone.utc)


# ======================= Préparation des données =============================
print("Chargement 40 symboles (36 mois, patch v5)...", flush=True)
SD = {s: v4.SymData(s) for s in SYMS_V8}
sd_btc = SD["BTCUSDT"]
BTC_IDX = {ts: i for i, ts in enumerate(sd_btc.t)}
N_BTC = sd_btc.n

base_day0 = sd_btc.t[0] // 86400000
start_btc = next(i for i in range(N_BTC)
                 if (sd_btc.t[i] // 86400000) - base_day0 >= 60)
start_btc = min(start_btc + 24, N_BTC - 1)
t_split = sd_btc.t[start_btc] + int(0.60 * (sd_btc.t[-1] - sd_btc.t[start_btc]))
months_btc = (sd_btc.t[-1] - sd_btc.t[start_btc]) / 86400000 / 30.4375
print(f"Fenêtre BTC : {utc(sd_btc.t[start_btc]):%Y-%m-%d} -> "
      f"{utc(sd_btc.t[-1]):%Y-%m-%d} ({months_btc:.1f} mois) | "
      f"frontière IS/OOS : {utc(t_split):%Y-%m-%d}\n", flush=True)


def start_of(sd):
    """Fenêtre de trading d'un symbole : 60 jours de chauffe puis +24 h."""
    b0 = sd.t[0] // 86400000
    si = next((i for i in range(sd.n)
               if (sd.t[i] // 86400000) - b0 >= 60), sd.n - 1)
    return min(si + 24, sd.n - 1)


# ============================ Flux (alphas) ==================================
def def_A1(pos, sd, i):
    c1, e1 = sd.m["c1"][i], sd.m["e1t"][i]
    if c1 is None or e1 is None:
        return None
    if (pos["side"] == 1 and c1 < e1) or (pos["side"] == -1 and c1 > e1):
        return "trendflip"
    return None


def def_A4(pos, sd, i):
    st_k = sd.get_k("st", sd.close_idx4[i])
    if st_k is None:
        return None
    if (pos["side"] == 1 and st_k == -1) or (pos["side"] == -1 and st_k == 1):
        return "flipST"
    return None


def def_A3(pos, sd, i):
    c4 = sd.get_k("c4", sd.close_idx4[i])
    e4z = sd.get_k("e4z", sd.close_idx4[i])
    if c4 is None or e4z is None:
        return None
    if (pos["side"] == 1 and c4 < e4z) or (pos["side"] == -1 and c4 > e4z):
        return "avortee"
    return None


def make_flows():
    f = {}
    c = __import__("types").SimpleNamespace()
    c.name, c.kind, c.stop_range, c.trail = "A1", "h1", v4.STOP_RANGE["A1"], "h1_24"
    c.signal = lambda sd, i, k=None: v4.signal_A1(sd, i)
    c.defensive = def_A1
    f["A1"] = c
    c = __import__("types").SimpleNamespace()
    c.name, c.kind, c.stop_range, c.trail = "A4", "h4", v4.STOP_RANGE["A4"], "h4_5"
    c.signal = lambda sd, i, k=None: v4.signal_A4(sd, i, sd.close_idx4[i])
    c.defensive = def_A4
    f["A4"] = c
    c = __import__("types").SimpleNamespace()
    c.name, c.kind, c.stop_range, c.trail = "A3", "h4", v4.STOP_RANGE["A3"], "h4_5"
    c.signal = lambda sd, i, k=None: v4.signal_A3(sd, i, sd.close_idx4[i])
    c.defensive = def_A3
    f["A3"] = c
    return f


FLOWS = make_flows()
FLOW_SCOPE = {"A1": PREM, "A4": set(SYMS_V8), "A3": set(SYMS_V8)}


# ========================= Harnais (adapté v8) ===============================
def run_stream(sd, cand, si, exitc, gate_th):
    """Flux isolé (alpha, symbole). Identique harnais v7, plus :
    - contexte BTC mappé par timestamp (univers non aligné en longueur) ;
    - échelle de sortie paramétrable (levier L2) ;
    - gate volatilité BTC D1 (levier L1), appliqué à toutes les entrées ;
    - meta.btc_atrd1 enregistré à chaque entrée (calibration L1)."""
    t, o, h, l, c = sd.t, sd.o, sd.h, sd.l, sd.c
    n = sd.n
    kind, trail = cand.kind, cand.trail
    tp1m, tp2m = exitc["tp1_mult"], exitc["tp2_mult"]
    tp1f, tp2f = exitc["tp1_frac"], exitc["tp2_frac"]
    trail4 = exitc["trail4"]
    pos = None
    q_entry = None
    trades = []
    eq = CFG["initialCapital"]
    eq_peak = eq
    day_t = day_eq = None
    week_t = week_eq = None
    total_fees = total_fund = 0.0

    def leg(px_fill, fee_rate, q, reason, ti):
        nonlocal eq, total_fees
        fee = q * px_fill * fee_rate
        total_fees += fee
        pnl_leg = (px_fill - pos["entry"]) * q * pos["side"] - fee
        eq += pnl_leg
        pos["pnl"] += pnl_leg
        pos["qty"] -= q
        pos["legs"].append((ti, px_fill, q, reason))

    for i in range(si, n):
        ti = t[i]
        if day_t is None:
            day_t, day_eq, week_t, week_eq = ti, eq, ti, eq
        if ti - day_t >= 86400000:
            day_t, day_eq = ti, eq
        day_loss = max(0.0, (1 - eq / day_eq) * 100) if day_eq > 0 else 0.0
        if ti - week_t >= 604800000:
            week_t, week_eq = ti, eq
        week_loss = max(0.0, (1 - eq / week_eq) * 100) if week_eq > 0 else 0.0
        breakers_ok = day_loss < CFG["dailyStop"] and week_loss < CFG["weeklyStop"]

        # ---- 1. funding
        if pos is not None and ti % (8 * B1H) == 0:
            pay = pos["qty"] * o[i] * sd.f_rate[i] * pos["side"]
            pos["pnl"] -= pay
            total_fund -= pay
            eq -= pay

        # ---- 2. sorties protectrices (stop d'abord, pessimiste)
        if pos is not None:
            hi, lo, op = h[i], l[i], o[i]
            s = pos["side"]
            stop_touch = lo <= pos["cur_stop"] if s == 1 else hi >= pos["cur_stop"]
            tp1_touch = (not pos["tp1_done"]) and \
                (hi >= pos["tp1_px"] if s == 1 else lo <= pos["tp1_px"])
            tp2_touch = (not pos["tp2_done"]) and \
                (hi >= pos["tp2_px"] if s == 1 else lo <= pos["tp2_px"])
            if stop_touch:
                fill = min(op, pos["cur_stop"]) * (1 - CFG["slip"]) if s == 1 \
                    else max(op, pos["cur_stop"]) * (1 + CFG["slip"])
                reason = "stop" if not (pos["tp1_done"] and pos["tp2_done"]) \
                    else "trail"
                leg(fill, CFG["taker"], pos["qty"], reason, ti)
                trades.append(close_pos(pos, i, "stop"))
                pos = None
            else:
                if tp1_touch:
                    fill = max(op, pos["tp1_px"]) if s == 1 else min(op, pos["tp1_px"])
                    leg(fill, CFG["maker"], min(pos["qty0"] * tp1f, pos["qty"]),
                        "tp1", ti)
                    pos["tp1_done"] = True
                if tp2_touch and pos["qty"] > 0:
                    fill = max(op, pos["tp2_px"]) if s == 1 else min(op, pos["tp2_px"])
                    leg(fill, CFG["maker"], min(pos["qty0"] * tp2f, pos["qty"]),
                        "tp2", ti)
                    pos["tp2_done"] = True
                if pos["qty"] <= 1e-12:
                    trades.append(close_pos(pos, i, "tps"))
                    pos = None

        # ---- 3. sortie signal (au close préc.)
        if pos is not None and pos.get("q_close"):
            fill = o[i] * (1 - CFG["slip"]) if pos["side"] == 1 \
                else o[i] * (1 + CFG["slip"])
            leg(fill, CFG["taker"], pos["qty"], pos["q_close"], ti)
            trades.append(close_pos(pos, i, pos["q_close"]))
            pos = None

        # ---- 4. entrée au marché (signal de la bougie préc.)
        if q_entry is not None and pos is None:
            s = q_entry["side"]
            fill = o[i] * (1 + CFG["slip"]) if s == 1 else o[i] * (1 - CFG["slip"])
            fee = q_entry["qty"] * fill * CFG["taker"]
            total_fees += fee
            eq -= fee
            dist = abs(fill - q_entry["stop"])
            pos = dict(side=s, qty=q_entry["qty"], qty0=q_entry["qty"],
                       entry=fill, stop0=q_entry["stop"], pnl=-fee,
                       risk_usd=q_entry["qty"] * dist,
                       tp1_px=fill + s * tp1m * dist,
                       tp2_px=fill + s * tp2m * dist,
                       tp1_done=False, tp2_done=False, cur_stop=q_entry["stop"],
                       q_close=None, legs=[], meta=q_entry.get("meta"),
                       t_in=ti, alpha=cand.name, sym=sd.sym)
            q_entry = None

        # ---- 5. contrôle liquidation (marge isolée 10x)
        if pos is not None:
            notional = pos["qty"] * c[i]
            margin = notional / CFG["nomLev"]
            if pos["side"] == 1:
                pliq = pos["entry"] - (margin - CFG["mmr"] * notional) / pos["qty"]
                if l[i] <= pliq:
                    fill = min(o[i], pliq)
                    leg(fill, CFG["taker"], pos["qty"], "liquidation", ti)
                    trades.append(close_pos(pos, i, "liquidation"))
                    pos = None
            else:
                pliq = pos["entry"] + (margin - CFG["mmr"] * notional) / pos["qty"]
                if h[i] >= pliq:
                    fill = max(o[i], pliq)
                    leg(fill, CFG["taker"], pos["qty"], "liquidation", ti)
                    trades.append(close_pos(pos, i, "liquidation"))
                    pos = None

        eq_mark = eq + (pos["qty"] * (c[i] - pos["entry"]) * pos["side"]
                        if pos else 0.0)
        eq_peak = max(eq_peak, eq_mark)

        # ---- 6. phase close : trail, défenses, signaux
        is_h4_close = (ti % B4) == B4 - B1H
        if pos is not None:
            stop_now = pos["entry"] if pos["tp1_done"] else pos["stop0"]
            if pos["tp2_done"]:
                if trail.startswith("h1"):
                    w = int(trail.split("_")[1])
                    lo_w = min(l[max(0, i - w + 1):i + 1])
                    hi_w = max(h[max(0, i - w + 1):i + 1])
                elif is_h4_close:
                    k = sd.close_idx4[i]
                    lo_w = min(sd.b4[3][max(0, k - trail4 + 1):k + 1])
                    hi_w = max(sd.b4[2][max(0, k - trail4 + 1):k + 1])
                else:
                    lo_w = hi_w = None
                if lo_w is not None:
                    if pos["side"] == 1:
                        stop_now = max(stop_now,
                                       lo_w * (1 - CFG["trailBufPct"] / 100))
                    else:
                        stop_now = min(stop_now,
                                       hi_w * (1 + CFG["trailBufPct"] / 100))
            pos["cur_stop"] = stop_now
            if cand.defensive is not None and pos.get("q_close") is None:
                if cand.kind == "h1" or is_h4_close:
                    reason = cand.defensive(pos, sd, i)
                    if reason:
                        pos["q_close"] = reason

        if pos is None and q_entry is None and breakers_ok:
            sig = None
            if kind == "h1":
                sig = cand.signal(sd, i)
            elif is_h4_close:
                sig = cand.signal(sd, i, sd.close_idx4[i])
            if sig:
                j = BTC_IDX.get(ti)
                ad = sd_btc.m["atr1dpct"][j] if j is not None else None
                # gate L1 : volatilité BTC D1 minimale (toutes paires)
                if gate_th is not None and (ad is None or ad < gate_th):
                    sig = None
                # filtre directionnel BTC (paires non-BTC, miroir v5)
                elif sd.sym != "BTCUSDT":
                    btc_c1 = sd_btc.m["c1"][j] if j is not None else None
                    btc_e1 = sd_btc.m["e1t"][j] if j is not None else None
                    if btc_c1 is None or btc_e1 is None:
                        sig = None
                    else:
                        btc_up = btc_c1 > btc_e1
                        ok = btc_up if sig[0] == 1 else (not btc_up)
                        if ok and kind == "h1":
                            adx1 = sd_btc.m["adx1"][j] if j is not None else None
                            directionnel = adx1 is None or adx1 > CHOP_ADX_MIN
                            if directionnel and adx1 is not None and j is not None \
                                    and sd_btc.m["atr1dpct"][j] is not None:
                                disp = abs(btc_c1 / btc_e1 - 1) * 100
                                if disp < CHOP_DISP_FAC * sd_btc.m["atr1dpct"][j]:
                                    directionnel = False
                            ok = ok and directionnel
                        if not ok:
                            sig = None
            if sig:
                side, stop, meta = (list(sig) + [None])[:3]
                px = c[i]
                dist = abs(px - stop)
                if dist > 0:
                    dist_pct = dist / px * 100
                    lo_r, hi_r = cand.stop_range
                    atrpct = sd.m["atr4pct"][i]
                    atr_ok = atrpct is None or dist_pct >= 0.7 * atrpct
                    if lo_r <= dist_pct <= hi_r and atr_ok:
                        risk_usd = eq * CFG["riskPct"] / 100
                        qty = min(risk_usd / dist, eq * CFG["maxEffLev"] / px)
                        if qty * px >= CFG["minNotional"]:
                            j = BTC_IDX.get(ti)
                            ad = sd_btc.m["atr1dpct"][j] if j is not None else None
                            meta = dict(meta or {})
                            meta["btc_atrd1"] = ad
                            q_entry = dict(side=side, stop=stop, qty=qty, meta=meta)
    if pos is not None:
        leg(c[-1] * (1 - CFG["slip"]) if pos["side"] == 1
            else c[-1] * (1 + CFG["slip"]), CFG["taker"], pos["qty"], "fin", t[-1])
        trades.append(close_pos(pos, n - 1, "fin"))
    return trades, total_fees, total_fund


def close_pos(pos, i, reason):
    qsum = sum(q for _, _, q, _ in pos["legs"])
    exit_avg = (sum(px * q for _, px, q, _ in pos["legs"]) / qsum) if qsum \
        else pos["entry"]
    t_out = pos["legs"][-1][0] if pos["legs"] else 0
    R = pos["pnl"] / pos["risk_usd"] if pos["risk_usd"] > 0 else 0.0
    return dict(key=f"{pos['alpha']}:{pos['sym']}", side=pos["side"],
                t_in=pos["t_in"], t_out=t_out, entry=pos["entry"],
                exit_avg=exit_avg, risk_usd=pos["risk_usd"], pnl=pos["pnl"],
                R=R, legs=list(pos["legs"]), reason=reason,
                meta=pos.get("meta"), alpha=pos["alpha"], sym=pos["sym"])


def block_stats(trs):
    if not trs:
        return dict(n=0, wr=0.0, pf=0.0, er=0.0, som=0.0)
    rs = [t["R"] for t in trs]
    g = sum(r for r in rs if r > 0)
    lo = -sum(r for r in rs if r < 0)
    return dict(n=len(rs), wr=100.0 * sum(1 for r in rs if r > 0) / len(rs),
                pf=g / lo if lo > 0 else float("inf"),
                er=sum(rs) / len(rs), som=sum(rs))


def fmt(st):
    pf = f"{st['pf']:.2f}" if st["pf"] != float("inf") else "inf"
    return (f"n={st['n']:4d}  WR={st['wr']:5.1f}%  PF={pf:>5s}  "
            f"E[R]={st['er']:+.3f}  somme={st['som']:+.1f}R")


# ================== PHASE A : rejeu V0 sur 40 paires =========================
print("=" * 78)
print("PHASE A — flux v5 sur 40 paires (échelle V0, sans gate)")
print("=" * 78)
streams = [(a, s) for a in FLOWS for s in FLOW_SCOPE[a]]
_ck_a = os.path.join(OUT, "_ck_trades_v0.pkl")
if os.path.exists(_ck_a):
    with open(_ck_a, "rb") as f:
        trades_v0 = pickle.load(f)
    print("(checkpoint Phase A rechargé)")
else:
    trades_v0 = []
    for a, sym in streams:
        trs, _, _ = run_stream(SD[sym], FLOWS[a], start_of(SD[sym]), EXIT_V0, None)
        for tr in trs:
            tr["pool"] = "main" if sym in PREM else "sat"
            trades_v0.append(tr)
    with open(_ck_a, "wb") as f:
        pickle.dump(trades_v0, f)
print(f"V0 : {len(trades_v0)} trades sur {len(streams)} flux x 36 mois\n")

for scope_name, sel in (("main BTC/ETH", lambda t: t["pool"] == "main"),
                        ("sat alts (38)", lambda t: t["pool"] == "sat")):
    for a in ("A1", "A4", "A3"):
        trs_a = [t for t in trades_v0 if a == t["alpha"] and sel(t)]
        is_t = [t for t in trs_a if t["t_in"] < t_split]
        oos_t = [t for t in trs_a if t["t_in"] >= t_split]
        print(f"  {scope_name:14s} {a} : IS  {fmt(block_stats(is_t))}")
        print(f"  {'':14s} {' ':2s}  OOS {fmt(block_stats(oos_t))}")
print()

# EDGE PAR ANNÉE (sat, déploiement élargi)
print("--- EDGE PAR ANNÉE (pool sat V0) ---")
for yr in (2020, 2021, 2022, 2023, 2024, 2025, 2026):
    trs_y = [t for t in trades_v0 if t["pool"] == "sat"
             and utc(t["t_in"]).year == yr]
    print(f"  {yr} : {fmt(block_stats(trs_y))}")
print()

# ================== PHASE B : levier L1 (gate volatilité) ====================
print("=" * 78)
print("PHASE B — levier L1 : gate volatilité BTC D1 (calibré IS -> OOS)")
print("=" * 78)
sat_v0 = [t for t in trades_v0 if t["pool"] == "sat"]
is_sat = [t for t in sat_v0 if t["t_in"] < t_split]
# distribution de référence : BTC atr1dpct sur les barres IS uniquement
ref = [x for k, x in zip(range(len(sd_btc.t)), sd_btc.m["atr1dpct"])
       if x is not None and sd_btc.t[k] < t_split and k >= start_btc]
ref_sorted = sorted(ref)
def pct_ref(p):
    return ref_sorted[min(len(ref_sorted) - 1, int(p * len(ref_sorted)))]
gate_res = {}
best = None
for tag in GATE_CANDIDATES:
    th = pct_ref({"p50": 0.50, "p60": 0.60, "p70": 0.70, "p80": 0.80}[tag])
    sel_is = [t for t in is_sat if t["meta"]["btc_atrd1"] is not None
              and t["meta"]["btc_atrd1"] >= th]
    sel_oos = [t for t in sat_v0 if t["t_in"] >= t_split
               and t["meta"]["btc_atrd1"] is not None
               and t["meta"]["btc_atrd1"] >= th]
    s_is, s_oos = block_stats(sel_is), block_stats(sel_oos)
    ok_oos = (s_oos["n"] >= 20 and s_oos["er"] >= 0.10 and s_oos["pf"] >= 1.25
              and s_oos["som"] > 0)
    ok_is = (s_is["n"] >= 40 and s_is["er"] > 0)
    gate_res[tag] = dict(th=th, IS=s_is, OOS=s_oos, ok_is=bool(ok_is),
                         ok_oos=bool(ok_oos))
    pf_i = f"{s_is['pf']:.2f}" if s_is["pf"] != float("inf") else "inf"
    pf_o = f"{s_oos['pf']:.2f}" if s_oos["pf"] != float("inf") else "inf"
    print(f"  {tag} (θ={th:.2f} %) : IS  n={s_is['n']:4d} PF={pf_i:>5s} "
          f"E[R]={s_is['er']:+.3f} | OOS n={s_oos['n']:4d} PF={pf_o:>5s} "
          f"E[R]={s_oos['er']:+.3f}  {'OK' if ok_is and ok_oos else 'rejeté'}")
    if ok_is and ok_oos and (best is None or s_is["er"] > gate_res[best]["IS"]["er"]):
        best = tag
s_base_is, s_base_oos = block_stats(is_sat), block_stats(
    [t for t in sat_v0 if t["t_in"] >= t_split])
print(f"  référence sans gate : IS {fmt(s_base_is)}")
print(f"                       OOS {fmt(s_base_oos)}")
gate_th = gate_res[best]["th"] if best else None
print(f"  => L1 : {'RETENU θ=' + format(gate_th, '.2f') + '%' if best else 'REJETÉ (V0 conservé)'}\n")

# ================== PHASE C : levier L2 (échelle de sortie) ==================
print("=" * 78)
print("PHASE C — levier L2 : échelle de sortie (décision IS, confirmation OOS)")
print("=" * 78)
var_res = {}
for vname, exitc in EXIT_VARIANTS.items():
    if vname == "V0":
        trs_v = trades_v0
    else:
        _ck_v = os.path.join(OUT, f"_ck_trades_{vname}.pkl")
        if os.path.exists(_ck_v):
            with open(_ck_v, "rb") as f:
                trs_v = pickle.load(f)
            print(f"  (checkpoint {vname} rechargé)")
        else:
            trs_v = []
            for a, sym in streams:
                trs, _, _ = run_stream(SD[sym], FLOWS[a], start_of(SD[sym]),
                                       exitc, None)
                for tr in trs:
                    tr["pool"] = "main" if sym in PREM else "sat"
                    trs_v.append(tr)
            with open(_ck_v, "wb") as f:
                pickle.dump(trs_v, f)
    sel = [t for t in trs_v if t["pool"] == "sat"]
    s_is = block_stats([t for t in sel if t["t_in"] < t_split])
    s_oos = block_stats([t for t in sel if t["t_in"] >= t_split])
    pf_i = f"{s_is['pf']:.2f}" if s_is["pf"] != float("inf") else "inf"
    pf_o = f"{s_oos['pf']:.2f}" if s_oos["pf"] != float("inf") else "inf"
    ok_oos = (s_oos["n"] >= 20 and s_oos["er"] >= 0.10 and s_oos["pf"] >= 1.25
              and s_oos["som"] > 0)
    var_res[vname] = dict(IS=s_is, OOS=s_oos, ok_oos=bool(ok_oos))
    print(f"  {vname} : IS  n={s_is['n']:4d} PF={pf_i:>5s} E[R]={s_is['er']:+.3f} "
          f"somme={s_is['som']:+.1f}R | OOS n={s_oos['n']:4d} PF={pf_o:>5s} "
          f"E[R]={s_oos['er']:+.3f}")
s0 = var_res["V0"]["IS"]
cands = [v for v in ("V1", "V2", "V3")
         if var_res[v]["IS"]["n"] >= 40
         and var_res[v]["IS"]["som"] > s0["som"]
         and var_res[v]["IS"]["er"] > s0["er"]
         and var_res[v]["OOS"]["er"] >= 0.10
         and var_res[v]["OOS"]["pf"] >= 1.25
         and var_res[v]["OOS"]["som"] > 0]
best_v = max(cands, key=lambda v: var_res[v]["IS"]["som"]) if cands else None
print(f"  => L2 : {'RETENU ' + best_v if best_v else 'REJETÉ (V0 conservé)'}\n")

# ================== RUN FINAL : pool v8 ======================================
print("=" * 78)
print(f"RUN FINAL — échelle {best_v or 'V0'}, gate "
      f"{'θ=' + format(gate_th, '.2f') + '%' if gate_th is not None else 'off'}")
print("=" * 78)
exitc = EXIT_VARIANTS[best_v] if best_v else EXIT_V0
_ck_f = os.path.join(OUT, "_ck_trades_final.pkl")
if best_v is None and gate_th is None:
    trades_f = trades_v0
elif os.path.exists(_ck_f):
    with open(_ck_f, "rb") as f:
        trades_f = pickle.load(f)
    print("(checkpoint run final rechargé)")
else:
    trades_f = []
    for a, sym in streams:
        trs, _, _ = run_stream(SD[sym], FLOWS[a], start_of(SD[sym]),
                               exitc, gate_th)
        for tr in trs:
            tr["pool"] = "main" if sym in PREM else "sat"
            trades_f.append(tr)
    with open(_ck_f, "wb") as f:
        pickle.dump(trades_f, f)
all_tr = trades_f
main_tr = [t for t in all_tr if t["pool"] == "main"]
sat_tr = [t for t in all_tr if t["pool"] == "sat"]
print(f"POOL v8 : {len(all_tr)} trades ({len(main_tr)} main / {len(sat_tr)} sat)")
print(f"  main : {fmt(block_stats(main_tr))}")
print(f"  sat  : {fmt(block_stats(sat_tr))}")
print(f"  tot  : {fmt(block_stats(all_tr))}")
m12 = [t for t in all_tr if t["t_in"] >= sd_btc.t[-1] - 365 * 86400000]
print(f"  cadence flotte : {len(all_tr) / months_btc:.1f}/mois (historique) | "
      f"{len(m12) / 12.0:.1f}/mois (12 derniers mois)")
print()

print("--- EDGE PAR ANNÉE (pool v8 final) ---")
for yr in (2020, 2021, 2022, 2023, 2024, 2025, 2026):
    trs_y = [t for t in all_tr if utc(t["t_in"]).year == yr]
    print(f"  {yr} : {fmt(block_stats(trs_y))}")
print()
print("--- PAR ALPHA (pool v8 final) ---")
for a in ("A1", "A4", "A3"):
    trs_a = [t for t in all_tr if t["alpha"] == a]
    print(f"  {a} : {fmt(block_stats(trs_a))}")
print()

with open(os.path.join(OUT, "pool_v8_deep.pkl"), "wb") as f:
    pickle.dump(dict(trades=all_tr, start_btc=start_btc, t_split=t_split,
                     months=months_btc, t0=sd_btc.t[start_btc], t1=sd_btc.t[-1],
                     exit_variant=best_v or "V0", gate_th=gate_th,
                     levers=dict(L1=gate_res, L2={k: v for k, v in var_res.items()}),
                     universe=SYMS_V8), f)

with open(os.path.join(OUT, "research_v8_deep.json"), "w") as f:
    json.dump(dict(
        univers=len(SYMS_V8), flux=len(streams),
        fenetre=dict(debut=str(utc(sd_btc.t[start_btc])), fin=str(utc(sd_btc.t[-1])),
                     mois=months_btc, frontiere=str(utc(t_split))),
        levers=dict(L1_choisi=best, L1_theta=gate_th,
                    L1_detail={k: dict(th=v["th"], IS=v["IS"], OOS=v["OOS"],
                                       ok_is=v["ok_is"], ok_oos=v["ok_oos"])
                               for k, v in gate_res.items()},
                    L2_choisi=best_v,
                    L2_detail={k: dict(IS=v["IS"], OOS=v["OOS"], ok_oos=v["ok_oos"])
                               for k, v in var_res.items()}),
        pool=dict(n=len(all_tr), n_main=len(main_tr), n_sat=len(sat_tr),
                  er_main=block_stats(main_tr)["er"],
                  er_sat=block_stats(sat_tr)["er"],
                  er_total=block_stats(all_tr)["er"],
                  cadence_hist=len(all_tr) / months_btc,
                  cadence_12m=len(m12) / 12.0,
                  par_annee={str(yr): block_stats([t for t in all_tr
                                                   if utc(t["t_in"]).year == yr])
                             for yr in (2020, 2021, 2022, 2023, 2024, 2025, 2026)},
                  par_alpha={a: block_stats([t for t in all_tr if t["alpha"] == a])
                             for a in ("A1", "A4", "A3")})),
        f, indent=2, ensure_ascii=False)

with open(os.path.join(OUT, "trades_v8_deep.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["flux", "entree_utc", "sortie_utc", "sens", "entree_px",
                "sortie_px_moy", "risque_usd", "pnl_usd_net", "R", "pool",
                "btc_atrd1", "sorties"])
    for tr in sorted(all_tr, key=lambda x: x["t_in"]):
        ad = (tr.get("meta") or {}).get("btc_atrd1")
        w.writerow([tr["key"], str(utc(tr["t_in"])), str(utc(tr["t_out"])),
                    "long" if tr["side"] == 1 else "short",
                    f"{tr['entry']:.2f}", f"{tr['exit_avg']:.2f}",
                    f"{tr['risk_usd']:.3f}", f"{tr['pnl']:.4f}",
                    f"{tr['R']:.3f}", tr.get("pool", ""),
                    "" if ad is None else f"{ad:.2f}",
                    "|".join(f"{rr}:{px:.2f}x{q:.6f}"
                             for _, px, q, rr in tr["legs"])])
print(f"Exports -> {OUT}/ (research_v8_deep.json, pool_v8_deep.pkl, trades_v8_deep.csv)")
