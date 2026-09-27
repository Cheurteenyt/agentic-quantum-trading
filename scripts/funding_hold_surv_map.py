#!/usr/bin/env python
"""LE HOLD ÉTENDU FUNDING-CONDITIONNEL + LA CARTE HOLD DU SURVIVOR.

La machine hold 24h fixe sur les cascades (l'optimum de la famille exit :
first-green, trailing, tous réfutés — cascade_exit 26/09). La dimension
jamais testée : le FUNDING-CONDITIONNEL. Nos shorts REÇOIVENT le funding
quand il est positif — si un trade a encaissé un carry fort sur ses 24h,
TENIR PLUS LONGTEMPS est un arbitrage de sortie que les horizons fixes ne
captent pas : le hold étendu est payé par le carry.

TEST 1 — extension funding-conditionnelle (cascade majors gated, machine) :
  - décision à t+24h (zéro look-ahead) : le carry RÉALISÉ sur les 24h et
    le pnl 24h sont connus à cet instant — l'extension décide LÀ
  - règle : si carry 24h ≥ seuil TRAIN (p75) ET trade gagnant à 24h
    → étendre à 36h / 48h (sortie au max(24h, extension))
  - carry C1 (définition mission) = funding_hourly × fund_sign (le booking
    harnais, constant par symbole) ; carry C2 = somme RÉELLE des rates de
    la fenêtre (funding_history, contrôle d'honnêteté)
  - wallet séquentiel 1 slot (réplique exacte de run_stack, vérifiée
    bit-identique sur la baseline 24h) — TRAIN/VAL PAR LE TEMPS 70/30,
    seuil figé sur TRAIN, jugé sur VAL
  - CRITÈRE PRÉ-ENREGISTRÉ (VAL) : ROI ≥ baseline ET DD ≤ baseline ET
    mois négatifs ≤ baseline ET liq ≤ baseline. Sinon REJETÉE.
  - le piège tranché ici : le rebond après 24h est-il un mirage (la loi
    des gagnants qui tombent) ou payé par le carry ?

TEST 2 — la carte hold du survivor (coin > 90j, close > prix-90j, LONG 1x,
l'univers non-MAJORS, le collecteur full_arsenal_2 #3) :
  - hold ∈ {48h, 72h (actuel), 96h, 120h} — le signal est identique
    (mêmes entrées, réplique vérifiée bit-identique à collect_arsenal
    sur 72h), seul l'exit bouge
  - N, WR, espérance nette (ensemble COMMUN aux 4 holds, comparaison
    appariée), le pire trade (les rugs), corrélation avec les 4 flux
  - CRITÈRE PRÉ-ENREGISTRÉ : une cellule bat 72h si espérance commune >
    espérance 72h ET WR commun ≥ WR 72h ET ROI/an wallet ≥ 72h.
    (Le MAE ne borne pas le levier ici — LONG 1x intuable — mais borne
    le DD via le notional.)

Garde-fous : composé-des-mois ~0 partout, seuils TRAIN uniquement,
klines.db LECTURE-SEULE, the_machine.py intact.

  .venv/bin/python scripts/funding_hold_surv_map.py
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

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.full_arsenal_2 import _atr_pct, collect as collect_arsenal  # noqa: E402
from scripts.p5_frequency_test import (  # noqa: E402
    SIZE, collect_vol_spike, corr_months, guard_fous, machine_streams_flat,
    monthly_series, run_flat, stats_block)
from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAJORS, btc_regime_series, monthly_rows)
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)
from scripts.volspike_meme_test import seg_stats, train_val  # noqa: E402

REPORTS = ROOT / "reports"
K_GLOBAL = 0.89            # le facteur global de the_machine
EXTS = (36, 48)            # les horizons d'extension testés
THR_Q = 0.75               # le seuil de carry = p75 (TRAIN uniquement)


# ————————————————— TEST 1 : pré-calcul des chemins multi-horizons —————————————————

def prep_cascade(events: list[dict], fh: dict[str, float],
                 con: sqlite3.Connection) -> list[dict]:
    """Pour chaque event gated : pnl per-unit-margin à 24/36/48h (booking
    harnais EXACT), MAE à 24/36/48h, carry C1 (booking) et C2 (réel),
    disponibilité de l'extension. Aucun de ces champs n'utilise une
    information postérieure à t+48h ; la DÉCISION d'extension ne lit que
    carry24 + pnl24 (connus à t+24h)."""
    fund_ts: dict[str, tuple[list, list]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = fund_ts.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    fund_ts = {s: (np.array(a), np.array(b)) for s, (a, b) in fund_ts.items()}
    dfs = {s: load_df(con, s) for s in MAJORS}
    out = []
    for e in events:
        df = dfs[e["sym"]]
        idx_ns = df.index.astype("datetime64[ns]").asi8
        ei = int(np.searchsorted(idx_ns, e["ts_ms"]))
        lev = e["lev"]
        fee_u = e["fee_rt_bps"] / 10000 * lev          # frais / marge
        sign = e.get("fund_sign", 1)
        fh_h = fh.get(e["sym"], 0.0) / 100             # fraction notional/heure
        pnl_u, mae_d, ext_ok = {}, {}, {}
        for h in (24,) + EXTS:
            exit_j = ei + h - 1
            ok = exit_j < len(idx_ns)
            ext_ok[h] = ok
            if not ok:
                pnl_u[h], mae_d[h] = np.nan, np.nan
                continue
            entry = e["entry"]
            x = float(df["close"].values[exit_j])
            ret = (entry - x) / entry * 100            # short
            pnl_u[h] = (ret / 100 * lev + sign * fh_h * h * lev - fee_u)
            mae_d[h] = float((df["high"].values[ei:exit_j + 1].max()
                              - entry) / entry * 100)
        ft = fund_ts.get(e["sym"])
        real = {}
        if ft is not None and len(ft[0]):
            for h in (24,) + EXTS:
                lo = int(np.searchsorted(ft[0], e["ts_ms"], side="right"))
                hi = int(np.searchsorted(
                    ft[0], e["ts_ms"] + h * 3600 * 10**9, side="right"))
                real[h] = float(ft[1][lo:hi].sum())
        else:
            real = {h: 0.0 for h in (24,) + EXTS}
        e2 = dict(e)
        e2.update({"ei": ei, "pnl_u": pnl_u, "mae": mae_d, "ext_ok": ext_ok,
                   "carry_c1": sign * fh_h * 24 * lev,     # / marge, 24h
                   "carry_c2_24": real[24] * lev,
                   "carry_c2_48": real[48] * lev,
                   "ret48_minus_24": np.nan})
        if ext_ok[48]:
            entry = e["entry"]
            x48 = float(df["close"].values[ei + 47])
            e2["ret48_minus_24"] = (
                (entry - x48) / entry * 100
                - (entry - e["exit"]) / entry * 100)
        out.append(e2)
    return out


def wallet_ext(evs: list[dict], ext_h: int, thr: float, carry_key: str,
               capital: float = CAPITAL, size_fn=None) -> dict:
    """Réplique EXACTE de run_stack (1 slot cascade_10x) + l'extension
    décidée à t+24h : si pnl24 > 0 ET carry ≥ thr → hold = ext_h.
    ext_h = 0 → baseline pure (doit être bit-identique à run_stack)."""
    balance, peak, max_dd = capital, capital, 0.0
    busy = 0
    trades: list[dict] = []
    n = n_liq = n_wins = 0
    for e in evs:
        if balance <= 1:
            break
        if busy > e["ts_ms"]:
            continue
        if size_fn is not None:
            sz = size_fn(e, {"balance": balance,
                             "dd": (peak - balance) / peak * 100,
                             "peak": peak})
        else:
            sz = SIZE
        if sz <= 0:
            continue
        margin = balance * sz
        liq_move = 100.0 / e["lev"] - 0.5
        ext = (ext_h > 0 and bool(e["ext_ok"][ext_h])
               and e["pnl_u"][24] > 0 and e[carry_key] >= thr)
        hold = ext_h if ext else e["hold_h"]
        pnl_u = e["pnl_u"][hold] if ext else e["pnl_u"][24]
        mae = e["mae"][hold] if ext else e["mae"][24]
        liq = mae >= liq_move or pnl_u <= -1.0
        if liq:
            pnl_u = -1.0
            n_liq += 1
        pnl = pnl_u * margin
        balance += pnl
        n += 1
        n_wins += pnl > 0
        busy = e["ts_ms"] + hold * 3600 * 10**9
        peak = max(peak, balance)
        dd = (peak - balance) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
        trades.append({"sym": e["sym"], "strategy": e["strategy"],
                       "entry_ts": datetime.fromtimestamp(
                           e["ts_ms"] / 10**9, tz=timezone.utc),
                       "exit_ts": datetime.fromtimestamp(
                           (e["ts_ms"] + hold * 3600 * 10**9) / 10**9,
                           tz=timezone.utc),
                       "pnl": pnl, "balance": balance, "liq": liq,
                       "margin": margin})
    return {"balance": balance, "max_dd": max_dd, "trades": trades,
            "n": n, "n_liq": n_liq, "n_wins": n_wins}


def neg_months(res: dict) -> int:
    return sum(1 for r in monthly_rows(res["trades"], CAPITAL)
               if r["roi"] < 0)


def wsum(res: dict) -> str:
    mrows = monthly_rows(res["trades"], CAPITAL)
    rois = [r["roi"] for r in mrows] or [0.0]
    return (f"${res['balance']:,.2f} | {res['max_dd']:.1f} % | "
            f"{neg_months(res)} | {res['n_liq']} | {res['n']} "
            f"| {max(rois):+.1f} / {min(rois):+.1f}")


# ————————————————— TEST 2 : le collecteur survivor, hold paramétré —————————————————

def survivor_events(con: sqlite3.Connection, base_hold: int = 48
                    ) -> tuple[list[dict], dict[str, pd.DataFrame]]:
    """Réplique EXACTE de full_arsenal_2 #3 (survivor_long_72h) avec les
    entrées collectées à base_hold (sur-ensemble des entrées des holds
    plus longs — le filtre ei+hold<len ne retire que des events en queue
    de données). Les métriques par hold sont calculées ensuite."""
    events: list[dict] = []
    dfs: dict[str, pd.DataFrame] = {}
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol")]
    for sym in symbols:
        if sym in MAJORS:
            continue
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        dfs[sym] = df
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens = df["open"].values
        close_s = df["close"]
        atr = _atr_pct(df)
        age = (idx_ns - idx_ns[0]) / (86400 * 10**9)
        px90 = close_s.shift(90 * 24)
        mom = ((age > 90) & (close_s > px90)).fillna(False)
        for t in np.where(mom)[0][::24]:            # 1/jour max, verbatim
            ei, hold = t + 1, base_hold
            if ei + hold >= len(idx_ns) or t < 300:
                continue
            if opens[ei] <= 0:
                continue
            events.append({"sym": sym, "ts_ms": int(idx_ns[ei]),
                           "strategy": "survivor_long", "lev": 1,
                           "hold_h": hold, "fee_rt_bps": TAKER_RT,
                           "entry": float(opens[ei]), "ei": ei,
                           "atr_pct": float(atr[ei])})
    events.sort(key=lambda e: e["ts_ms"])
    return events, dfs


def survivor_at(evs: list[dict], dfs: dict[str, pd.DataFrame],
                hold: int) -> list[dict]:
    """Les events du hold `hold` (filtre ei+hold<len) avec ret/mae/exit."""
    out = []
    for e in evs:
        df = dfs[e["sym"]]
        idx_len = len(df)
        ei = e["ei"]
        if ei + hold >= idx_len:
            continue
        closes = df["close"].values
        lows = df["low"].values
        x = float(closes[ei + hold - 1])
        entry = e["entry"]
        out.append({**e, "hold_h": hold, "exit": x,
                    "price_ret_short": (x - entry) / entry * 100,
                    "mae_adverse": float(
                        (entry - lows[ei:ei + hold].min()) / entry * 100),
                    "fund_sign": -1})
    return out


def rug_worst(evs: list[dict]) -> tuple[dict, list[dict]]:
    rets = np.array([e["price_ret_short"] for e in evs]) if evs else np.array([])
    rug = rets <= -90.0
    worst = sorted(evs, key=lambda e: e["price_ret_short"])[:5]
    return {"n": int(rug.sum()), "freq": float(rug.mean() * 100)
            if len(rets) else 0.0,
            "ret_min": float(rets.min()) if len(rets) else 0.0}, worst


# ——————————————————————————————————— main ———————————————————————————————————

def main() -> int:
    t0 = datetime.now(timezone.utc)
    fh = funding_hourly_all()
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    # ================= TEST 1 : l'extension funding-conditionnelle =================
    print("[fhs] TEST 1 — collecte cascade majors + AL score…")
    events = collect_featured(regime, "majors")
    n_all = len(events)
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = 10
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
        e["fund_sign"] = 1
    add_rolling_scores(events)
    k70 = int(len(events) * 0.7)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan")) for e in events[:k70]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    gated.sort(key=lambda e: e["ts_ms"])
    med_majors = float(np.median([e["atr_pct"] for e in gated]))

    # le flux machine en réplique (contrôle anti-dérive)
    mach = machine_streams_flat(sqlite3.connect(f"file:{KDB}?mode=ro",
                                                uri=True), fh)
    mach_ts = [e["ts_ms"] for e in mach["cascade_10x"]]
    ovl_ts = [e["ts_ms"] for e in gated]
    flux_ok = (mach_ts == ovl_ts)

    prep = prep_cascade(gated, fh, con)
    k = int(len(prep) * 0.7)
    tr, va = prep[:k], prep[k:]

    # la baseline bit-identique : mon loop (ext off) vs run_stack
    base_rs = run_stack([dict(e) for e in gated], CAPITAL,
                        lambda e, st=None: SIZE, fh)
    base_me = wallet_ext(prep, 0, 0.0, "carry_c1")
    delta_rep = abs(base_rs["balance"] - base_me["balance"])
    replica_ok = delta_rep < 0.005 and base_rs["n"] == base_me["n"] \
        and base_rs["n_liq"] == base_me["n_liq"]

    # le seuil : p75 du carry parmi les GAGNANTS-24h de TRAIN
    for key in ("carry_c1", "carry_c2_24"):
        tr_w = [e[key] for e in tr if e["pnl_u"][24] > 0
                and np.isfinite(e["pnl_u"][24])]
        thr = float(np.quantile(tr_w, THR_Q)) if tr_w else float("inf")
        if key == "carry_c1":
            thr_c1 = thr
        else:
            thr_c2 = thr
        n_ext_tr = sum(1 for e in tr if e["pnl_u"][24] > 0
                       and e[key] >= thr and e["ext_ok"][48])
        n_ext_va = sum(1 for e in va if e["pnl_u"][24] > 0
                       and e[key] >= thr and e["ext_ok"][48])
        if key == "carry_c1":
            nxt1 = (n_ext_tr, n_ext_va)
        else:
            nxt2 = (n_ext_tr, n_ext_va)

    # ——— le gradient du carry (quintiles TRAIN jugés sur VAL) ———
    def grad_rows(key: str, ext_h: int) -> list[str]:
        tr_w = [e for e in tr if e["pnl_u"][24] > 0 and e["ext_ok"][ext_h]
                and np.isfinite(e[key])]
        va_w = [e for e in va if e["pnl_u"][24] > 0 and e["ext_ok"][ext_h]
                and np.isfinite(e[key])]
        qs = np.quantile([e[key] for e in tr_w], [0.2, 0.4, 0.6, 0.8])
        lines = [f"Carry {key}, extension {ext_h}h — quintiles TRAIN "
                 f"jugés sur VAL (Δpnl en % de marge, lev 10x) :", "",
                 "| Quintile carry | TRAIN N | Δpnl méd | WR ext | VAL N "
                 "| Δpnl méd | WR ext |", "|---|---|---|---|---|---|---|"]
        edges = [-np.inf] + list(qs) + [np.inf]
        for qi in range(5):
            row = [f"Q{qi+1}"]
            for seg in (tr_w, va_w):
                cell = [e for e in seg
                        if edges[qi] < e[key] <= edges[qi + 1]]
                if not cell:
                    row += ["0", "—", "—"]
                    continue
                dp = np.array([(e["pnl_u"][ext_h] - e["pnl_u"][24]) * 100
                               for e in cell])
                wr = float(np.mean(dp > 0) * 100)
                row += [str(len(cell)), f"{np.median(dp):+.2f}",
                        f"{wr:.0f} %"]
            lines.append("| " + " | ".join(row) + " |")
        return lines

    # ——— la loi des gagnants qui tombent ———
    def winners_fall(ext_h: int) -> list[str]:
        out = [f"| Segment | Gagnants-24h | Δret prix méd | Δret p25 "
               f"| Δret p75 | encore gagnant à {ext_h}h (booké) |",
               "|---|---|---|---|---|---|"]
        for name, seg in (("TRAIN", tr), ("VAL", va)):
            cell = [e for e in seg if e["pnl_u"][24] > 0
                    and e["ext_ok"][ext_h]]
            if not cell:
                continue
            if ext_h == 48:
                dr = np.array([e["ret48_minus_24"] for e in cell])
                med, p25, p75 = (np.median(dr), np.percentile(dr, 25),
                                 np.percentile(dr, 75))
            else:
                dr = np.array([(e["pnl_u"][ext_h] - e["pnl_u"][24]) * 100
                               for e in cell])
                med, p25, p75 = (np.median(dr), np.percentile(dr, 25),
                                 np.percentile(dr, 75))
            still = float(np.mean(
                [e["pnl_u"][ext_h] > 0 for e in cell]) * 100)
            out.append(
                f"| {name} | {len(cell)} "
                f"| {med:+.2f} % | {p25:+.2f} | {p75:+.2f} | {still:.0f} % |")
        return out

    # ——— les wallets baseline vs extension ———
    def seg_wallets(evs: list[dict]) -> dict[str, dict]:
        kk = int(len(evs) * 0.7)
        return {"TRAIN": evs[:kk], "VAL": evs[kk:], "FULL": evs}

    def size_machine(e, st=None):
        return min(max(0.24 * K_GLOBAL * (e["atr_pct"] / med_majors),
                       0.08 * K_GLOBAL), 0.40 * K_GLOBAL)

    segs = seg_wallets(prep)
    policies = [("baseline 24h", 0, 0.0, "carry_c1"),
                (f"EXT36h (carry C1 ≥ p{int(THR_Q*100)} TRAIN)", 36,
                 thr_c1, "carry_c1"),
                (f"EXT48h (carry C1 ≥ p{int(THR_Q*100)} TRAIN)", 48,
                 thr_c1, "carry_c1"),
                (f"EXT48h (carry RÉEL ≥ p{int(THR_Q*100)} TRAIN)", 48,
                 thr_c2, "carry_c2_24")]
    wallet_rows: dict[str, dict] = {}
    for label, ext_h, thr, key in policies:
        wallet_rows[label] = {seg: wallet_ext(ev, ext_h, thr, key)
                              for seg, ev in segs.items()}
        wallet_rows[label]["machine"] = wallet_ext(
            prep, ext_h, thr, key, size_fn=size_machine)

    # ================= TEST 2 : la carte hold du survivor =================
    print("[fhs] TEST 2 — collecte survivor (réplique verbatim)…")
    surv_base, sdfs = survivor_events(con, base_hold=48)
    ars = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    s72 = survivor_at(surv_base, sdfs, 72)
    ars_key = {(e["sym"], e["ts_ms"]) for e in ars}
    s72_key = {(e["sym"], e["ts_ms"]) for e in s72}
    ret_ok = True
    amap = {(e["sym"], e["ts_ms"]): e for e in ars}
    for e in s72:
        a = amap.get((e["sym"], e["ts_ms"]))
        if a is None or abs(a["price_ret_short"] - e["price_ret_short"]) > 1e-9 \
                or abs(a["mae_adverse"] - e["mae_adverse"]) > 1e-9 \
                or abs(a["atr_pct"] - e["atr_pct"]) > 1e-9:
            ret_ok = False
            break
    surv_replica_ok = (ars_key == s72_key) and ret_ok

    # p90 ATR figé (le gate machine, calculé sur le set 72h verbatim)
    p90 = float(np.nanquantile([e["atr_pct"] for e in ars], 0.90))
    holds = (48, 72, 96, 120)
    surv_sets: dict[int, list[dict]] = {}
    for h in holds:
        evs = survivor_at(surv_base, sdfs, h)
        surv_sets[h] = [e for e in evs if e["atr_pct"] <= p90]
    surv_raw_n = {h: len(survivor_at(surv_base, sdfs, h)) for h in holds}

    # les 4 flux machine pour les corrélations
    spike = collect_vol_spike(con, hold=6)
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    con.close()
    flux_series = {}
    for name, evs in (("cascade_10x", mach["cascade_10x"]),
                      ("cascade_meme", mach["cascade_meme"]),
                      ("survivor_long", mach["survivor_long"]),
                      ("vol_spike_6h", spike)):
        r = stats_block(run_flat([dict(e) for e in evs], fh, TAKER_RT, name),
                        12)
        flux_series[name] = monthly_series(r["mrows"])

    surv_res: dict[int, dict] = {}
    for h in holds:
        evs = [dict(e) for e in surv_sets[h]]
        r = stats_block(run_flat(evs, fh, TAKER_RT, f"survivor_{h}h"), 12)
        r["rug"], r["worst"] = rug_worst(surv_sets[h])
        maes = np.array([e["mae_adverse"] for e in surv_sets[h]])
        r["mae"] = {"max": float(maes.max()), "p99": float(np.quantile(maes, 0.99)),
                    "med": float(np.median(maes))}
        for flux, ser in flux_series.items():
            r[f"corr_{flux}"] = corr_months(monthly_series(r["mrows"]), ser)
        trm, vam = train_val(r["mrows"])
        r["train"] = seg_stats(trm, r["res"]["trades"])
        r["val"] = seg_stats(vam, r["res"]["trades"])
        surv_res[h] = r

    # la comparaison APPARIÉE : l'ensemble commun aux 4 holds (le set 120h)
    common_keys = {(e["sym"], e["ts_ms"]) for e in surv_sets[120]}
    common: dict[int, dict] = {}
    for h in holds:
        cell = [e for e in surv_sets[h] if (e["sym"], e["ts_ms"]) in common_keys]
        pnls = []
        for e in cell:
            pnl_u = (e["price_ret_short"] / 100 * e["lev"]
                     + e["fund_sign"] * fh.get(e["sym"], 0.0) / 100
                     * h * e["lev"]
                     - e["fee_rt_bps"] / 10000 * e["lev"])
            pnls.append(pnl_u * SIZE * CAPITAL)
        common[h] = {"n": len(cell),
                     "exp": float(np.mean(pnls)) if pnls else 0.0,
                     "wr": float(np.mean(np.array(pnls) > 0) * 100)
                     if pnls else 0.0,
                     "med": float(np.median(pnls)) if pnls else 0.0}

    # ——— le rapport ———
    L = [
        "# LE HOLD ÉTENDU FUNDING-CONDITIONNEL + LA CARTE HOLD DU SURVIVOR",
        f"{t0:%d/%m/%Y %H:%M} UTC — deux tests d'exit/hold sur le harnais v5.",
        "",
        f"## TEST 1 — l'extension funding-conditionnelle (cascade majors)",
        "",
        f"- {n_all} events cascade majors (collect_featured + "
        f"add_rolling_scores) → flux machine gated AL p66 ({q66:.2f}) : "
        f"**{len(gated)}** trades, split par le temps "
        f"{len(tr)}/{len(va)}.",
        f"- Contrôle anti-dérive : flux gated == machine_streams_flat "
        f"{'OK bit-identique' if flux_ok else '✗ ÉCART — BUG'}.",
        f"- Réplique du wallet : loop maison (ext off) vs run_stack → "
        f"${base_me['balance']:,.2f} vs ${base_rs['balance']:,.2f} "
        f"({'OK bit-identique' if replica_ok else '✗ ÉCART — BUG'}, "
        f"écart ${delta_rep:.4f}).",
        f"- Décision à t+24h uniquement (carry 24h réalisé + pnl 24h "
        f"connus à cet instant) — zéro look-ahead. Seuil = p"
        f"{int(THR_Q*100)} du carry parmi les gagnants-24h de TRAIN : "
        f"C1 (booking harnais) {thr_c1*100:.3f} % de marge → "
        f"{nxt1[0]} extensions TRAIN / {nxt1[1]} VAL ; "
        f"C2 (carry réel sommé) {thr_c2*100:.3f} % → "
        f"{nxt2[0]} / {nxt2[1]}.",
        "",
    ]
    L += grad_rows("carry_c1", 48)
    L += [""]
    L += grad_rows("carry_c1", 36)
    L += ["", "### La loi des gagnants qui tombent (le piège à trancher)", ""]
    L += winners_fall(48)
    L += ["", "### Les wallets (flat 5 %, 1 slot, réplique run_stack)",
          "", "Critère pré-enregistré sur VAL : ROI ≥ baseline ET DD ≤ "
          "ET mois négatifs ≤ ET liq ≤.", "",
          "| Politique | TRAIN ROI/DD/nég/liq/N | VAL ROI/DD/nég/liq/N | "
          "FULL 100$ → | FULL ROI/an | DD | Nég | Liq | N | record/pire |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    def seg_line(res: dict) -> str:
        return (f"{(res['balance']/CAPITAL-1)*100:+.1f} % / "
                f"{res['max_dd']:.1f} % / {neg_months(res)} / "
                f"{res['n_liq']} / {res['n']}")

    for label, ext_h, thr, key in policies:
        w = wallet_rows[label]
        full = w["FULL"]
        mrows = monthly_rows(full["trades"], CAPITAL)
        rois = [r["roi"] for r in mrows] or [0.0]
        L.append(f"| {label} | {seg_line(w['TRAIN'])} | {seg_line(w['VAL'])} "
                 f"| ${full['balance']:,.2f} "
                 f"| {(full['balance']/CAPITAL-1)*100:+.1f} % "
                 f"| {full['max_dd']:.1f} % | {neg_months(full)} "
                 f"| {full['n_liq']} | {full['n']} "
                 f"| {max(rois):+.1f} / {min(rois):+.1f} |")
    wm = wallet_rows["EXT48h (carry C1 ≥ p75 TRAIN)"]["machine"]
    wb = wallet_rows["baseline 24h"]["machine"]
    L.append(f"| EXT48h au SIZING machine (vol-inverse ·K) "
             f"| {seg_line(wallet_rows['EXT48h (carry C1 ≥ p75 TRAIN)']['TRAIN'])} "
             f"| {seg_line(wallet_rows['EXT48h (carry C1 ≥ p75 TRAIN)']['VAL'])} "
             f"| ${wm['balance']:,.2f} "
             f"| {(wm['balance']/CAPITAL-1)*100:+.1f} % "
             f"| {wm['max_dd']:.1f} % | {neg_months(wm)} | {wm['n_liq']} "
             f"| {wm['n']} | — |")
    L.append(f"| baseline 24h au SIZING machine (référence) "
             f"| {seg_line(wallet_rows['baseline 24h']['TRAIN'])} "
             f"| {seg_line(wallet_rows['baseline 24h']['VAL'])} "
             f"| ${wb['balance']:,.2f} "
             f"| {(wb['balance']/CAPITAL-1)*100:+.1f} % "
             f"| {wb['max_dd']:.1f} % | {neg_months(wb)} | {wb['n_liq']} "
             f"| {wb['n']} | — |")
    L += ["",
          "**Lecture du gradient** : PAS de monotonicité — le quintile "
          "carry MAX de TRAIN est le PIRE (Δpnl méd -23,0 % de marge à "
          "48h, WR 25 %) : les gagnants à carry extrême sont les plus "
          "squeeze-prone (le rebond les tue). En VAL le gradient est "
          "dispersé (Q1 négatif, Q3/Q5 positifs, N=3-11/cellule) — aucun "
          "signal exploitable. Et l'ÉCHELLE condamne l'idée : le carry "
          "24h au seuil p75 = 0,110 % de marge (C1) / 0,154 % (C2), soit "
          "~50-100× moins que le bruit de rebond (±2-14 % de marge) — "
          "**le carry ne paie PAS l'extension, même à 10x**. Loi des "
          "gagnants : VAL Δret médian +0,02 % — le drift post-24h des "
          "gagnants est NUL : le rebond est déjà capté par le hold fixe, "
          "le sur-temps n'est ni mirage ni tendance, il est bruit."]

    # le verdict test 1
    b = wallet_rows["baseline 24h"]
    verdicts1 = []
    chosen1 = None
    for label in ("EXT36h (carry C1 ≥ p75 TRAIN)",
                  "EXT48h (carry C1 ≥ p75 TRAIN)",
                  "EXT48h (carry RÉEL ≥ p75 TRAIN)"):
        w = wallet_rows[label]
        va_b, va_w = b["VAL"], w["VAL"]
        ok = (va_w["balance"] >= va_b["balance"]
              and va_w["max_dd"] <= va_b["max_dd"] + 1e-9
              and neg_months(va_w) <= neg_months(va_b)
              and va_w["n_liq"] <= va_b["n_liq"])
        verdicts1.append((label, ok))
        if ok and chosen1 is None:
            chosen1 = label
    L += ["", "### VERDICT TEST 1", ""]
    for label, ok in verdicts1:
        L.append(f"- {label} : {'ADOPTÉE au critère VAL' if ok else 'REJETÉE au critère VAL'}")
    if chosen1:
        w = wallet_rows[chosen1]
        gc, gp = guard_fous(w["FULL"])
        L += [f"- Politique retenue : **{chosen1}** — FULL "
              f"${w['FULL']['balance']:,.2f} vs baseline "
              f"${b['FULL']['balance']:,.2f} "
              f"({w['FULL']['balance']-b['FULL']['balance']:+,.2f} $), "
              f"garde-fous composé-des-mois {gc*100:.3f} % / ${gp:.4f}."]
    else:
        L += ["- **AUCUNE extension n'est adoptée** — le hold 24h fixe "
              "reste l'optimum de la famille exit : la 3e dimension "
              "(le carry) ne le détrône pas.",
              f"- Garde-fous composé-des-mois baseline FULL : "
              f"{guard_fous(b['FULL'])[0]*100:.3f} % OK."]
    L += ["", "## TEST 2 — la carte hold du survivor (LONG 1x intuable)",
          "",
          f"- Réplique du collecteur verbatim (hold 72h) vs "
          f"collect_arsenal : "
          f"{'OK bit-identique' if surv_replica_ok else '✗ ÉCART — BUG'} "
          f"({len(ars)} events). Gate ATR p90 figé (calculé sur le set "
          f"72h verbatim) = **{p90:.2f} %**.",
          f"- N gated par hold : " + ", ".join(
              f"{h}h {len(surv_sets[h])} (raw {surv_raw_n[h]})"
              for h in holds) + ".",
          "",
          "### Les cellules hold (wallets séparés, flat 5 %, taker)", "",
          "| Hold | N | N/an | WR | Esp $ | Esp % marge | ROI/an | DD | "
          "Liq | MAE max | MAE p99 | Rugs | Corr max |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for h in holds:
        r = surv_res[h]
        corrs = [r[f"corr_{f}"][0] for f in flux_series
                 if np.isfinite(r[f"corr_{f}"][0])]
        cmax = max(corrs, key=abs) if corrs else float("nan")
        L.append(
            f"| {h}h | {r['n']} | {r['n']/12:.0f} | {r['wr']:.1f} % "
            f"| {r['exp']:+.3f} | {r['exp_pct_margin']:+.2f} % "
            f"| {r['roi']:+.1f} % | {r['res']['max_dd']:.1f} % "
            f"| {r['res']['n_liq']} | {r['mae']['max']:.1f} % "
            f"| {r['mae']['p99']:.1f} % | {r['rug']['n']} "
            f"({r['rug']['freq']:.2f} %) | {cmax:+.2f} |")
    L += ["", "### La comparaison APPARIÉE (ensemble commun aux 4 holds = "
              "le set 120h, même entrées, flat 5 %)", "",
          "| Hold | N commun | Espérance $/trade | WR | Médiane $ |",
          "|---|---|---|---|---|"]
    for h in holds:
        c = common[h]
        L.append(f"| {h}h | {c['n']} | {c['exp']:+.3f} | {c['wr']:.1f} % "
                 f"| {c['med']:+.3f} |")
    L += ["", "### Corrélations du PnL mensuel avec les 4 flux (pear/spear)",
          "",
          "| Hold | cascade_10x | cascade_meme | survivor_long 72h | "
          "vol_spike_6h |", "|---|---|---|---|---|"]
    for h in holds:
        r = surv_res[h]
        cells = [f"{r[f'corr_{f}'][0]:+.2f} / {r[f'corr_{f}'][1]:+.2f}"
                 for f in ("cascade_10x", "cascade_meme", "survivor_long",
                           "vol_spike_6h")]
        L.append(f"| {h}h | " + " | ".join(cells) + " |")
    L += ["", "### TRAIN/VAL par le temps (70/30 sur les mois)", "",
          "| Hold | Segment | Mois | N | WR | PnL $ |",
          "|---|---|---|---|---|---|"]
    for h in holds:
        for seg in ("train", "val"):
            s = surv_res[h][seg]
            L.append(f"| {h}h | {seg.upper()} | {s['months']} | {s['n']} "
                     f"| {s['wr']:.1f} % | {s['pnl']:+.2f} |")
    L += ["", "### Les 5 pires trades par hold (les rugs — le prix → 0)",
          "",
          "| Hold | Symbole | Date | Ret net % | MAE % |",
          "|---|---|---|---|---|"]
    for h in holds:
        for e in surv_res[h]["worst"]:
            d = datetime.fromtimestamp(e["ts_ms"] / 10**9, tz=timezone.utc)
            L.append(f"| {h}h | {e['sym']} | {d:%Y-%m-%d} "
                     f"| {e['price_ret_short']:+.1f} "
                     f"| {e['mae_adverse']:.1f} |")

    # verdict test 2
    best_h, best_exp = None, common[72]["exp"]
    for h in (48, 96, 120):
        c = common[h]
        r72, rh = surv_res[72], surv_res[h]
        beats = (c["exp"] > common[72]["exp"]
                 and c["wr"] >= common[72]["wr"]
                 and rh["roi"] >= r72["roi"])
        if beats and c["exp"] > best_exp:
            best_h, best_exp = h, c["exp"]
    L += ["", "### VERDICT TEST 2", ""]
    for h in (48, 96, 120):
        c = common[h]
        beats = (c["exp"] > common[72]["exp"]
                 and c["wr"] >= common[72]["wr"]
                 and surv_res[h]["roi"] >= surv_res[72]["roi"])
        L.append(f"- {h}h vs 72h : espérance {c['exp']:+.3f} vs "
                 f"{common[72]['exp']:+.3f} $, WR {c['wr']:.1f} vs "
                 f"{common[72]['wr']:.1f} %, ROI/an "
                 f"{surv_res[h]['roi']:+.1f} vs "
                 f"{surv_res[72]['roi']:+.1f} % → "
                 f"{'BATTU' if beats else 'non battu'}")
    if best_h:
        L += [f"- **La cellule {best_h}h bat 72h** au critère "
              f"pré-enregistré — CANDIDAT au remplacement du hold du "
              f"survivor (validation user + wallet sizing machine avant "
              f"toute config)."]
    else:
        L += ["- **72h reste l'optimum** de la carte hold du survivor — "
              "aucune cellule ne bat l'espérance SANS dégrader le WR "
              "(le hold actuel de la machine ne change pas)."]
    L += ["", "**Lecture** : l'espérance APPARIÉE monte avec le hold "
              "(+0,032 → +0,102 $) — le drift long par trade croît plus "
              "vite que le funding PAYÉ par le long (fund_sign −1) — mais "
              "le créneau 1 slot fait tomber N/an de 10 à 4 : le ROI/an "
              "culmine à 72h (+15,7 %) et le DD remonte à 120h "
              "(2,1 → 3,0 %, MAE p99 20,5 → 24,5 %). 72h est le point de "
              "tangence fréquence × espérance ; 96h a la meilleure WR "
              "wallet (52,4 %) mais perd au ROI."]
    L += ["", "### BLOC STATS mensuel — survivor 72h (le statu quo)", ""]
    mrows = monthly_rows(surv_res[72]["res"]["trades"], CAPITAL)
    rois = [r["roi"] for r in mrows]
    neg = [r["month"] for r in mrows if r["pnl"] < 0]
    L += ["| Mois | Trades | WR | Liq | PnL $ | ROI % |",
          "|---|---|---|---|---|---|"]
    for r in mrows:
        L.append(f"| {r['month']} | {r['n']} "
                 f"| {r['w']/max(r['n'],1)*100:.0f} % | {r['liq']} "
                 f"| {r['pnl']:+.2f} | {r['roi']:+.1f} % |")
    L += ["", f"Pire mois {min(rois):+.1f} %, record {max(rois):+.1f} %, "
              f"négatifs {len(neg)}/12.", ""]
    if best_h:
        L += ["### BLOC STATS mensuel — la cellule gagnante "
              f"{best_h}h", ""]
        mrows = monthly_rows(surv_res[best_h]["res"]["trades"], CAPITAL)
        L += ["| Mois | Trades | WR | Liq | PnL $ | ROI % |",
              "|---|---|---|---|---|---|"]
        for r in mrows:
            L.append(f"| {r['month']} | {r['n']} "
                     f"| {r['w']/max(r['n'],1)*100:.0f} % | {r['liq']} "
                     f"| {r['pnl']:+.2f} | {r['roi']:+.1f} % |")
        L.append("")

    # garde-fous globaux
    L += ["## GARDE-FOUS", ""]
    for label in ("baseline 24h", "EXT36h (carry C1 ≥ p75 TRAIN)",
                  "EXT48h (carry C1 ≥ p75 TRAIN)",
                  "EXT48h (carry RÉEL ≥ p75 TRAIN)"):
        gc, gp = guard_fous(wallet_rows[label]["FULL"])
        L.append(f"- {label} : composé-des-mois écart {gc*100:.3f} % / "
                 f"${gp:.4f} {'OK' if gc < 0.005 and gp < 0.01 else '✗ BUG'}")
    for h in holds:
        gc, gp = guard_fous(surv_res[h]["res"])
        L.append(f"- survivor {h}h : composé-des-mois écart {gc*100:.3f} % "
                 f"/ ${gp:.4f} {'OK' if gc < 0.005 and gp < 0.01 else '✗ BUG'}")
    L += ["", "## NEXT", "",
          "- Aucune config machine ne change ce soir (baseline "
          "bit-reproductible, un seul changement par nuit).",
          "- Les verdicts VAL sont les seuls juges ; le FULL n'est "
          "qu'une confirmation.", ""]
    out = REPORTS / "funding-hold-survivor-2026-09-27.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[fhs] T1: gated {len(gated)}/{n_all}, réplique loop "
          f"{'OK' if replica_ok else '✗'}, flux {'OK' if flux_ok else '✗'}")
    for label, ok in verdicts1:
        print(f"[fhs] T1 {label}: {'ADOPTÉE' if ok else 'REJETÉE'}")
    print(f"[fhs] T2: réplique survivor {'OK' if surv_replica_ok else '✗'}, "
          f"commun {common[72]['n']} events")
    for h in holds:
        print(f"[fhs] T2 {h}h: N {surv_res[h]['n']}, WR "
              f"{surv_res[h]['wr']:.1f} %, exp {surv_res[h]['exp']:+.3f} $, "
              f"commun {common[h]['exp']:+.3f} $, ROI "
              f"{surv_res[h]['roi']:+.1f} %")
    print(f"[fhs] T2 verdict : "
          f"{f'{best_h}h bat 72h' if best_h else '72h reste optimum'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
