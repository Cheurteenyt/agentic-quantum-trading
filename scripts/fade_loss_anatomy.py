#!/usr/bin/env python
"""FADE LOSS ANATOMY — l'anatomie des échecs du fade + l'exit conditionnel
côté perte (28/09). UNE ÉTUDE PROFONDE, pas un test rapide.

CONTEXTE (pré-enregistré). Le fade vol_spike_6h = le seul edge multi-régime
(3/4 trimestres positifs, Q3'26 mort = son meilleur +15,1 %, WR forward 62 %
sur n=13). SA FAIBLESSE MESURÉE : l'asymétrie des pertes — gagnants +1,73 %
moyen, perdants -3,66 %, pire -10,56 % (forward) ; le cumul forward est
négatif MALGRÉ le WR. LA QUESTION DU RECORD CERTAIN : réduire la queue
gauche du fade = l'edge devient solide dans tous les régimes.

PARTIE 1 — L'ANATOMIE (features ex-ante une par une, gradient TRAIN/VAL).
Corpus = la mécanique p5 exacte (range 1h ≥ 4× médiane 14j et ≥ 2,5 %,
fade de la direction, hold 6h, gate décile ATR recalculé DANS l'univers)
sur l'univers meme (1h hors MAJORS — variante A de volspike_meme_test,
le fade EST un flux memecoin : registre 27/09). Déclaration honnête : la
DB a grossi depuis le 27/09 — le même builder donnait 809 events alors,
il en donne ~5 000 aujourd'hui ; les 809 sont inclus dedans.
Split TRAIN/VAL PAR LE TEMPS 70/30 (cut = quantile 70 des ts).
Losers = ret6 < -2 % (notation directionnelle, hors coûts).
La barre : gradient MONOTONE sur TRAIN tenu sur VAL (quartiles coupés sur
TRAIN uniquement) + Spearman train/val. 6 features :
  (a) btc_ret24 (ex-ante) + btc pendant le hold (diagnostique ex-post) ;
  (b) l'âge du mouvement : streak d'heures rng ≥ 2×med finissant sur la
      bougie spike (age_h) + heures depuis le spike précédent (dist_prev) ;
  (c) le financement as-of : fund_income = côté × dernier rate connu avant
      l'entrée (SHORT +1 / LONG -1 ; > 0 = le fade REÇOIT le funding) ;
  (d) la force du range : mult = rng/med (≥ 4 par construction) ;
  (e) la pression taker DANS la bougie extrême : br_ext = taker_buy/volume
      de la bougie spike 1h (couverture 100 % — leçon 15m : TURBO/WIF seuls
      hors majors ont du 15m), side-ajustée : fade_pressure = br_ext pour
      un SHORT (les acheteurs poussés dans l'extrême = absorption →
      bounce), 1-br_ext pour un LONG (les vendeurs absorbés). Direction
      pré-enregistrée : fade_pressure ↑ → ret ↑. Sous-test 15m sur la
      couverture (déclarée).
  (f) le symbole (catégoriel : concentration des pertes).

PARTIE 2 — L'EXIT CONDITIONNEL CÔTÉ PERTE (structurellement nouveau).
Les sorties testées étaient INCONDITIONNELLES (tous à h=6h). Règle
candidate : SI perte ≥ seuil à h_chk → sortie à la CLOSE SUIVANTE (couper
tôt) ; SI gain (ou perte < seuil) → tenir jusqu'à 6h. Logique mesurée :
les perdants du fade CONTINUENT, les gagnants ne doivent pas être coupés.
Cellules : h_chk ∈ {2h, 3h} × seuil ∈ {0,5 %, 1 %, 1,5 %} + baseline 6h.
Mesurées au harnais v5 (run_stack, 1x flat 5 % marge, TAKER, un créneau).
TRAIN/VAL stricte : une cellule passe si espérance nette ≥ baseline sur
TRAIN ET VAL, asymétrie améliorée, pire trade amélioré.

PARTIE 3 — LE JUGEMENT DU RECORD : config finale (filtre anatomique si un
feature tient + exit conditionnel s'il tient) vs baseline. BLOC STATS
complet : N, WR, liqs, ROI/an, DD, pire/record mois, mois négatifs,
asymétrie AVANT/APRÈS, pires trades, composé-des-mois ~0 (guard_fous),
espérance par trimestre (les 4 trimestres). CRITÈRE DU RECORD CERTAIN
(pré-enregistré) : espérance nette > 0 sur TRAIN ET VAL ET les 4
trimestres, ratio gain/perte ≥ 0,7, pire trade > -6 %.

L'HONNÊTETÉ : le forward n=13 = confirmation, pas preuve ; le backtest =
la preuve. Multiple comparisons : 6 features × 6 cellules — la barre VAL
stricte est le garde-fou.

  .venv/bin/python scripts/fade_loss_anatomy.py
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
from scripts.p5_frequency_test import (  # noqa: E402
    MAJORS, guard_fous)
from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
SIZE = 0.05                       # marge flat 5 % — la convention « seul »
HOLD = 6                          # hold 6h — le validé, intouché
K_RNG, ABS_MIN, WIN = 4.0, 2.5, 336   # seuils p5 INTOUCHÉS
FEE_PCT = TAKER_RT / 100.0        # 0,28 % du notionnel (AR taker)
LOSE_THR = -2.0                   # la définition pré-enregistrée du perdant
REC_THR = 1.0                     # le gagnant (pour le ratio d'asymétrie)
EXITS = [(2, 0.0), (2, 0.5), (2, 1.0), (2, 1.5),
         (3, 0.0), (3, 0.5), (3, 1.0), (3, 1.5)]


# ———————————————————————————— le corpus annoté ————————————————————————————

def build_corpus(con: sqlite3.Connection) -> list[dict]:
    """La mécanique p5 verbatim (collect_vol_spike variante A) + les
    features ex-ante + les chemins 7h (closes/highs/lows) pour l'exit."""
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol") if r[0] not in MAJORS]
    # BTC (contexte) + funding as-of (ts en NS — leçon ts_ms)
    bdf = load_df(con, "BTCUSDT")
    b_idx = bdf.index.astype("datetime64[ns]").asi8
    b_close = bdf["close"].values
    f_ts: list[int] = []
    f_rt: list[float] = []
    for t, r in con.execute(
            "SELECT funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            f_ts.append(t * 10**6 if t > 10**11 else t * 10**9)
            f_rt.append(float(r))
        except (TypeError, ValueError):
            continue
    f_ts_a, f_rt_a = np.array(f_ts), np.array(f_rt)
    # taker buy 1h par symbole (leçon ts_ms : open_time en MS, idx en NS)
    tbv: dict[str, dict[int, tuple[float, float]]] = {}
    for s, ot, tb_, v_ in con.execute(
            "SELECT symbol, open_time, taker_buy_volume, volume FROM klines "
            "WHERE interval='1h' AND taker_buy_volume IS NOT NULL"):
        tbv.setdefault(s, {})[int(ot)] = (float(tb_ or 0.0), float(v_ or 0.0))
    events: list[dict] = []
    atr_all: list[float] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < WIN + HOLD + 2:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens, highs, lows = (df["open"].values, df["high"].values,
                              df["low"].values)
        closes = df["close"].values
        tb_map = tbv.get(sym, {})
        close_s = df["close"]
        rng = ((df["high"] - df["low"]) / close_s * 100).values
        med = pd.Series(rng).rolling(WIN, min_periods=100).median().values
        with np.errstate(invalid="ignore"):
            sig = (rng >= K_RNG * med) & (rng >= ABS_MIN)
            hi_rng_arr = rng >= 2 * med
        body_up = (close_s >= df["open"]).values
        atr = (close_s.diff().abs().rolling(24).mean() / close_s * 100).values
        sig_ts: list[int] = []
        for t in np.where(sig)[0]:
            ei = t + 1
            if ei + HOLD >= len(idx_ns) or t < WIN:
                continue
            entry = opens[ei]
            if entry <= 0 or not np.isfinite(atr[ei]):
                continue
            if body_up[t]:                      # spike haussier → SHORT
                side, sign = "short", 1
            else:                               # spike baissier → LONG
                side, sign = "long", -1
            # — features ex-ante —
            j24 = int(np.searchsorted(b_idx, idx_ns[ei - 1])) - 1
            j24b = int(np.searchsorted(b_idx, idx_ns[ei - 25])) - 1
            btc_ret24 = ((b_close[j24] / b_close[j24b]) - 1) * 100 \
                if 0 <= j24b <= j24 < len(b_close) else float("nan")
            fo = int(np.searchsorted(f_ts_a, idx_ns[ei], side="right")) - 1
            fund_asof = f_rt_a[fo] * 100 if fo >= 0 else float("nan")
            # l'âge : streak d'heures rng ≥ 2×med finissant sur la spike
            age = 0
            k = t
            while k >= 0 and hi_rng_arr[k]:
                age += 1
                k -= 1
            prev = sig_ts[-1] if sig_ts else None
            dist_prev = (t - prev) if prev is not None else float("inf")
            sig_ts.append(t)
            mult = float(rng[t] / med[t]) if np.isfinite(med[t]) and med[t] \
                else float("nan")
            def br(i: int) -> float:
                bar = tb_map.get(int(idx_ns[i]) // 10**6)
                return float(bar[0] / bar[1] * 100) \
                    if bar and bar[1] > 0 else float("nan")
            br_ext = br(t)
            fp = br_ext if sign == 1 else (100 - br_ext
                                           if np.isfinite(br_ext)
                                           else float("nan"))
            events.append({
                "sym": sym, "ts_ms": int(idx_ns[ei]), "strategy": "fade",
                "lev": 1, "hold_h": HOLD, "fee_rt_bps": TAKER_RT,
                "entry": float(entry), "side": side, "fund_sign": sign,
                "atr_pct": float(atr[ei]), "mult": mult, "age_h": age,
                "dist_prev": dist_prev, "btc_ret24": btc_ret24,
                "fund_asof": fund_asof,
                "fund_income": sign * fund_asof if np.isfinite(fund_asof)
                else float("nan"),
                "br_ext": br_ext, "fade_pressure": fp,
                "br_pre": float(np.nanmean([br(t - 1), br(t - 2)])),
                "ret6": float((entry - closes[ei + HOLD - 1]) / entry * 100
                              if sign == 1
                              else (closes[ei + HOLD - 1] - entry) / entry * 100),
                "price_ret_short": float(
                    (entry - closes[ei + HOLD - 1]) / entry * 100 if sign == 1
                    else (closes[ei + HOLD - 1] - entry) / entry * 100),
                "mae6": float(max(
                    (highs[ei:ei + HOLD].max() - entry) / entry * 100 if sign == 1
                    else (entry - lows[ei:ei + HOLD].min()) / entry * 100, 0)),
                "mae_adverse": float(max(
                    (highs[ei:ei + HOLD].max() - entry) / entry * 100 if sign == 1
                    else (entry - lows[ei:ei + HOLD].min()) / entry * 100, 0)),
                "closes": [float(c) for c in closes[ei:ei + HOLD + 1]],
                "hi_lo": [float(x) for x in
                          (highs[ei:ei + HOLD + 1] if sign == 1
                           else lows[ei:ei + HOLD + 1])],
                "btc_hold": float((b_close[int(np.searchsorted(
                    b_idx, idx_ns[ei + HOLD - 1])) - 1] / b_close[j24]) - 1)
                * 100 if 0 <= j24 < len(b_close) else float("nan")})
            atr_all.append(float(atr[ei]))
    # gate décile ATR recalculé DANS l'univers (variante A, verbatim p5)
    p90 = float(np.nanquantile(atr_all, 0.90))
    events = [e for e in events if e["atr_pct"] <= p90]
    events.sort(key=lambda e: e["ts_ms"])
    return events


def net_ret(e: dict) -> float:
    """Le ret6 net de coûts (taker AR + funding moyen harnais) en % notionnel."""
    return e["ret6"] - FEE_PCT + e["fund_sign"] * \
        FH.get(e["sym"], 0.0) / 100 * HOLD


# ————————————————————— Partie 1 : l'anatomie ——————————————————————

def spearman(xs, ys) -> float:
    try:
        from scipy.stats import spearmanr
        return float(spearmanr(xs, ys).statistic)
    except Exception:
        xr, yr = pd.Series(xs).rank().values, pd.Series(ys).rank().values
        return float(np.corrcoef(xr, yr)[0, 1])


def monotone(v: list[float]) -> bool:
    """Monotone strict au sens utile : croissant OU décroissant sans plat."""
    up = all(v[i] <= v[i + 1] for i in range(len(v) - 1)) and v[0] < v[-1]
    dn = all(v[i] >= v[i + 1] for i in range(len(v) - 1)) and v[0] > v[-1]
    return up or dn


def anatomy_block(train: list[dict], val: list[dict], key: str,
                  label: str) -> tuple[list[str], bool]:
    """Quartiles coupés sur TRAIN : ret moyen, net moyen, taux de perte
    par bucket — la barre = gradient monotone TRAIN tenu VAL."""
    vals_tr = [e[key] for e in train if np.isfinite(e[key])]
    finite = [e for e in train if np.isfinite(e[key])]
    fin_val = [e for e in val if np.isfinite(e[key])]
    if len(finite) < 40 or len(fin_val) < 15:
        return ([f"| {label} | couverture insuffisante ({len(finite)}/"
                 f"{len(fin_val)}) | — | — | — | — | — | — |"], False)
    cuts = [float(q) for q in np.quantile(vals_tr, [0.25, 0.5, 0.75])]
    edges = [-np.inf] + cuts + [np.inf]
    rows, tr_means, va_means, ok_val = [], [], [], True
    for qi in range(4):
        bt = [e for e in finite if edges[qi] < e[key] <= edges[qi + 1]]
        bv = [e for e in fin_val if edges[qi] < e[key] <= edges[qi + 1]]
        if len(bt) < 8 or len(bv) < 5:
            ok_val = False
        mt = float(np.mean([e["ret6"] for e in bt])) if bt else float("nan")
        nt = float(np.mean([net_ret(e) for e in bt])) if bt else float("nan")
        lt = float(np.mean([e["ret6"] < LOSE_THR for e in bt])) * 100 if bt \
            else float("nan")
        mv = float(np.mean([e["ret6"] for e in bv])) if bv else float("nan")
        lv = float(np.mean([e["ret6"] < LOSE_THR for e in bv])) * 100 if bv \
            else float("nan")
        tr_means.append(mt)
        va_means.append(mv)
        rows.append(
            f"| Q{qi + 1} ({edges[qi]:.2f}–{edges[qi + 1]:.2f}) "
            f"| {len(bt)}/{len(bv)} | {mt:+.2f} | {nt:+.2f} | {lt:.1f} "
            f"| {mv:+.2f} | {lv:.1f} |")
    ok = monotone([x for x in tr_means if np.isfinite(x)]) and \
        monotone([x for x in va_means if np.isfinite(x)]) and ok_val
    rho_t = spearman([e[key] for e in finite], [e["ret6"] for e in finite])
    rho_v = spearman([e[key] for e in fin_val], [e["ret6"] for e in fin_val])
    head = [f"**{label}** (`{key}`) — monotone TRAIN+VAL : "
            f"{'**OUI**' if ok else 'non'} ; Spearman train {rho_t:+.2f} / "
            f"val {rho_v:+.2f}",
            "",
            "| Bucket (bornes TRAIN) | n TR/VA | ret TR | net TR | P(perte) TR "
            "| ret VA | P(perte) VA |",
            "|---|---|---|---|---|---|---|"]
    return head + rows + [""], ok


# ————————————— Partie 2 : l'exit conditionnel —————————————

def with_exit(events: list[dict], h_chk: int, thr: float) -> list[dict]:
    """La règle : perte ≥ thr à h_chk → sortie à la close suivante ;
    sinon tenir 6h. Recalcule ret, MAE (fenêtre réelle) et hold."""
    out = []
    for e in events:
        cl, hl = e["closes"], e["hi_lo"]
        entry, sign = e["entry"], e["fund_sign"]
        def sret(px: float) -> float:
            return (entry - px) / entry * 100 if sign == 1 \
                else (px - entry) / entry * 100
        u_chk = sret(cl[h_chk - 1])
        if u_chk <= -thr:                    # perdant → couper à la close +
            xj, hold = h_chk, h_chk + 1
        else:                                # gagnant / petit perdant → 6h
            xj, hold = HOLD - 1, HOLD
        ret = sret(cl[xj])
        mae = float(max((max(hl[:xj + 1]) - entry) / entry * 100
                        if sign == 1
                        else (entry - min(hl[:xj + 1])) / entry * 100, 0))
        g = dict(e)
        g.update({"price_ret_short": ret, "mae_adverse": mae, "hold_h": hold,
                  "exit": cl[xj], "cut": xj < HOLD - 1})
        out.append(g)
    return out


def run_wallet(events: list[dict], fee_rt: int = TAKER_RT) -> dict:
    evs = [dict(e) for e in events]
    for e in evs:
        e["fee_rt_bps"] = fee_rt
    res = run_stack(evs, CAPITAL, lambda e, st=None: SIZE, FH)
    return res


def trade_metrics(res: dict) -> dict:
    pnls = np.array([t["pnl"] for t in res["trades"]])
    if len(pnls) == 0:
        return {}
    # ret net % notionnel par trade (échelle du forward : +1,73 / -3,66) ;
    # alignement trades↔events par (sym, seconde d'entrée) — le harnais ne
    # prend qu'un sous-ensemble des events (créneau occupé)
    ev_map = {(e["sym"], e["ts_ms"] // 10**9): e for e in res["_evs"]}
    nets = []
    for t in res["trades"]:
        if t["liq"]:
            nets.append(-100.0)          # 1x : la liq = -100 % du notionnel
            continue
        e = ev_map.get((t["sym"], int(t["entry_ts"].timestamp())))
        if e is None:
            continue
        nets.append(e["price_ret_short"] - FEE_PCT
                    + e["fund_sign"] * FH.get(e["sym"], 0.0) / 100
                    * e["hold_h"])
    nets = np.array(nets)
    wins, losses = nets[nets > 0], nets[nets <= 0]
    mrows = monthly_rows(res["trades"], CAPITAL)
    return {"n": len(pnls), "wr": float((pnls > 0).mean() * 100),
            "exp": float(pnls.mean()),
            "net_mean": float(nets.mean()),
            "aw": float(wins.mean()) if len(wins) else 0.0,
            "al": float(losses.mean()) if len(losses) else 0.0,
            "ratio": float(wins.mean() / abs(losses.mean()))
            if len(wins) and len(losses) else float("nan"),
            "worst": float(nets.min()), "best": float(nets.max()),
            "liq": res["n_liq"], "roi": (res["balance"] / CAPITAL - 1) * 100,
            "dd": res["max_dd"], "mrows": mrows,
            "bal": res["balance"]}


# ————————————————————————————— le rapport —————————————————————————————

def fmt_bloc(m: dict, months_span: float) -> list[str]:
    pos = [r for r in m["mrows"] if r["pnl"] > 0]
    neg = [r for r in m["mrows"] if r["pnl"] <= 0]
    worst_m = min(m["mrows"], key=lambda r: r["pnl"]) if m["mrows"] else None
    best_m = max(m["mrows"], key=lambda r: r["pnl"]) if m["mrows"] else None
    roi_an = m["roi"] * 12 / max(months_span, 0.1)
    return [
        f"- Trades pris {m['n']} | WR {m['wr']:.1f} % | liqs {m['liq']} "
        f"| espérance {m['exp']:+.3f} $/trade ({m['net_mean']:+.2f} % "
        f"notionnel net)",
        f"- Asymétrie : gagnants {m['aw']:+.2f} % / perdants {m['al']:+.2f} %"
        f" → ratio {m['ratio']:.2f} | pire trade {m['worst']:+.2f} % "
        f"| meilleur {m['best']:+.2f} %",
        f"- ROI période {m['roi']:+.1f} % (≈ {roi_an:+.1f} %/an sur "
        f"{months_span:.1f} mois) | DD {m['dd']:.1f} % | wallet "
        f"$100 → ${m['bal']:.2f}",
        f"- Mois : {len(m['mrows'])} pris en compte, {len(neg)} négatifs "
        f"({', '.join(r['month'] for r in neg) or 'aucun'})"
        + (f" | pire {worst_m['month']} {worst_m['pnl']:+.2f} $"
           f" | record {best_m['month']} {best_m['pnl']:+.2f} $"
           if worst_m and best_m else ""),
    ]


def main() -> int:
    global FH
    t0 = datetime.now(timezone.utc)
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=60)
    FH = funding_hourly_all()
    print("[anat] construction du corpus annoté (mécanique p5, univers meme)…")
    events = build_corpus(con)
    con.close()
    ts = np.array([e["ts_ms"] for e in events])
    k = int(len(events) * 0.7)
    cut_ts = int(ts[k])
    train = events[:k]
    val = events[k:]
    d = datetime.fromtimestamp(cut_ts / 10**9, tz=timezone.utc)
    months_span = (ts.max() - ts.min()) / 10**9 / 86400 / 30.44
    n_lose = sum(1 for e in events if e["ret6"] < LOSE_THR)

    L = [
        "# FADE LOSS ANATOMY — l'anatomie des échecs + l'exit conditionnel",
        f"{t0:%d/%m/%Y %H:%M} UTC — harnais v5 (run_stack, entrée open t+1, "
        f"MAE fenêtre réelle, un créneau, 1x flat 5 % marge, TAKER 28 bps AR).",
        "",
        f"**Corpus** : mécanique p5 verbatim (range ≥ 4× médiane 14j et "
        f"≥ 2,5 %, fade direction, hold 6h, gate décile ATR recalculé dans "
        f"l'univers) sur 1h **hors MAJORS** (variante A volspike_meme — le "
        f"fade EST un flux memecoin, registre 27/09). DB actuelle = "
        f"**{len(events)} events** (le même builder donnait 809 au 27/09 — "
        f"la DB a grossi, les 809 sont inclus). Période "
        f"{datetime.fromtimestamp(ts.min()/10**9, tz=timezone.utc):%Y-%m-%d}"
        f" → {datetime.fromtimestamp(ts.max()/10**9, tz=timezone.utc):%Y-%m-%d}"
        f" ({months_span:.1f} mois).",
        "",
        f"**Split par le temps 70/30** : TRAIN {len(train)} / VAL {len(val)} "
        f"(cut {d:%Y-%m-%d %H:%M}). Perdants (ret < -2 %) : {n_lose} "
        f"({n_lose/len(events)*100:.1f} %). Baseline ret6 brut moyen "
        f"{np.mean([e['ret6'] for e in events]):+.3f} %, WR "
        f"{np.mean([e['ret6'] > 0 for e in events])*100:.1f} %.",
        "",
        "## PARTIE 1 — L'ANATOMIE (features ex-ante, gradient TRAIN→VAL)", ""]

    any_pass = {}
    feats = [
        ("btc_ret24", "(a) BTC 24h avant l'entrée (ex-ante)"),
        ("age_h", "(b) âge du mouvement (streak rng ≥ 2×med)"),
        ("dist_prev", "(b') heures depuis le spike précédent (même symbole)"),
        ("fund_income", "(c) funding as-of côté trade (> 0 = le fade reçoit)"),
        ("mult", "(d) force du range (multiplicateur exact ≥ 4×)"),
        ("fade_pressure", "(e) pression taker DANS l'extrême, side-ajustée"),
        ("br_ext", "(e') brut taker_buy % de la bougie spike (diagnostic)"),
    ]
    for key, label in feats:
        lines, ok = anatomy_block(train, val, key, label)
        any_pass[key] = (ok, label)
        L += lines
    btc_hold = [e["btc_hold"] for e in events if np.isfinite(e["btc_hold"])]
    L += [f"Diagnostique ex-post (pas un filtre) : BTC pendant le hold moyen "
          f"{np.mean(btc_hold):+.2f} % — corr ret6 "
          f"{spearman(btc_hold, [e['ret6'] for e in events if np.isfinite(e['btc_hold'])]):+.2f}.",
          ""]

    # ——— les pertes par symbole (f) ———
    L += ["**(f) Le symbole — la concentration des pertes** (top 12 par "
          "somme de ret perdus)", "",
          "| Symbole | n | WR | ret moyen | P(perte < -2 %) | ret < -2 % cumulés |",
          "|---|---|---|---|---|---|"]
    by_sym = {}
    for e in events:
        by_sym.setdefault(e["sym"], []).append(e)
    srows = []
    for s, es in by_sym.items():
        rets = np.array([e["ret6"] for e in es])
        srows.append((float(rets[rets < LOSE_THR].sum()), s, len(es),
                      float((rets > 0).mean() * 100), float(rets.mean()),
                      float((rets < LOSE_THR).mean() * 100)))
    for tot, s, n, wr, mr, pl in sorted(srows)[:12]:
        L.append(f"| {s} | {n} | {wr:.0f} % | {mr:+.2f} % | {pl:.0f} % "
                 f"| {tot:+.1f} % |")
    L += ["", "**LA QUESTION CENTRALE DE L'EXIT : les perdants du fade "
          "continuent-ils après h=2h ?** (contingence ex-post, tout le "
          "corpus — c'est la prémisse mesurée de la règle candidate)", "",
          "| État à 2h (unrealized) | n | ret6 moyen % | ret 2h→6h moyen % "
          "| P(ret6 < -2 %) |", "|---|---|---|---|---|"]
    for lab, lo_, hi_ in (("gain ≥ 0", 1e9, None), ("0 > u ≥ -0,5", 0, -0.5),
                          ("-0,5 > u ≥ -1", -0.5, -1.0),
                          ("-1 > u ≥ -2", -1.0, -2.0),
                          ("u < -2", -2.0, -1e9)):
        sel = []
        for e in events:
            entry, sign = e["entry"], e["fund_sign"]
            u = ((entry - e["closes"][1]) / entry * 100 if sign == 1
                 else (e["closes"][1] - entry) / entry * 100)
            if lab.startswith("gain"):
                if u >= 0:
                    sel.append(e)
            elif lab == "u < -2":
                if u < -2:
                    sel.append(e)
            elif lo_ > u >= hi_:
                sel.append(e)
        if not sel:
            continue
        r6 = np.array([e["ret6"] for e in sel])
        cont = []
        for e in sel:
            entry, sign = e["entry"], e["fund_sign"]
            u = ((entry - e["closes"][1]) / entry * 100 if sign == 1
                 else (e["closes"][1] - entry) / entry * 100)
            c = ((entry - e["closes"][5]) / entry * 100 if sign == 1
                 else (e["closes"][5] - entry) / entry * 100)
            cont.append(c - u)
        L.append(f"| {lab} | {len(sel)} | {r6.mean():+.2f} "
                 f"| {np.mean(cont):+.2f} "
                 f"| {(r6 < LOSE_THR).mean()*100:.1f} |")
    L += ["", "Lecture : un ret 2h→6h qui reste négatif dans les buckets "
          "perdants = la continuation mesurée (la règle aurait raison) ; "
          "un ret 2h→6h positif = le rebond revient APRÈS la perte de 2h "
          "(couper tôt détruit l'edge).", ""]

    L += ["", "## PARTIE 2 — L'EXIT CONDITIONNEL CÔTÉ PERTE", "",
          "Règle : perte ≥ seuil à h_chk → sortie à la CLOSE SUIVANTE ; "
          "sinon tenir 6h. 1x flat 5 %, TAKER, un créneau.", "",
          "| Cellule | N | WR | net/trade % | ratio G/P | pire % | liq | "
          "ROI/an | DD | net TR | net VA |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    base_res = run_wallet(events)
    base_res["_evs"] = events
    bm = trade_metrics(base_res)
    tr_cut, va_cut = k, len(events)
    ev_tr, ev_va = events[:tr_cut], events[tr_cut:]
    # baseline train/val : runs séparés
    bres_tr = run_wallet(ev_tr); bres_tr["_evs"] = ev_tr
    bres_va = run_wallet(ev_va); bres_va["_evs"] = ev_va
    bm_tr, bm_va = trade_metrics(bres_tr), trade_metrics(bres_va)
    ev_map_base = {(e["sym"], e["ts_ms"] // 10**9): e for e in events}
    L.append(f"| **baseline 6h** | {bm['n']} | {bm['wr']:.1f} % | "
             f"{bm['net_mean']:+.2f} | {bm['ratio']:.2f} | {bm['worst']:+.2f} "
             f"| {bm['liq']} | {bm['roi']*12/months_span:+.1f} % | "
             f"{bm['dd']:.1f} % | {bm_tr['net_mean']:+.2f} | "
             f"{bm_va['net_mean']:+.2f} |")
    cell_stats = {}
    for h_chk, thr in EXITS:
        evs = with_exit(events, h_chk, thr)
        res = run_wallet(evs); res["_evs"] = evs
        m = trade_metrics(res)
        rtr = run_wallet(with_exit(ev_tr, h_chk, thr))
        rtr["_evs"] = with_exit(ev_tr, h_chk, thr)
        rva = run_wallet(with_exit(ev_va, h_chk, thr))
        rva["_evs"] = with_exit(ev_va, h_chk, thr)
        m_tr, m_va = trade_metrics(rtr), trade_metrics(rva)
        cell_stats[(h_chk, thr)] = (m, m_tr, m_va)
        L.append(f"| h={h_chk}h thr={thr:.1f} % | {m['n']} | {m['wr']:.1f} % "
                 f"| {m['net_mean']:+.2f} | {m['ratio']:.2f} | "
                 f"{m['worst']:+.2f} | {m['liq']} | "
                 f"{m['roi']*12/months_span:+.1f} % | {m['dd']:.1f} % "
                 f"| {m_tr['net_mean']:+.2f} | {m_va['net_mean']:+.2f} |")
    L += [""]
    # ——— verdict des cellules ———
    L += ["**Verdict des cellules** (passe = net TR ≥ baseline TR ET net VA "
          "≥ baseline VA ET ratio ↑ ET pire trade ↑) :", ""]
    passing_cells = []
    for (h_chk, thr), (m, m_tr, m_va) in cell_stats.items():
        ok = (m_tr["net_mean"] > bm_tr["net_mean"]
              and m_va["net_mean"] >= bm_va["net_mean"]
              and m["ratio"] > bm["ratio"] and m["worst"] > bm["worst"])
        L.append(f"- h={h_chk}h thr={thr:.1f} % : net {m['net_mean']:+.2f} % "
                 f"(baseline {bm['net_mean']:+.2f}) — "
                 f"{'**PASS**' if ok else 'fail'}")
        if ok:
            passing_cells.append((h_chk, thr))
    L += [""]

    # ——— PARTIE 3 : le jugement ———
    # ——— les pires trades (l'identité de la queue gauche) ———
    L += ["**Les 5 pires trades du baseline wallet** (la queue gauche à "
          "réduire) :", ""]
    worst5 = sorted(zip(base_res["trades"],
                        [ev_map_base.get((t["sym"],
                                          int(t["entry_ts"].timestamp())))
                         for t in base_res["trades"]]),
                    key=lambda x: x[0]["pnl"])[:5]
    for t, e in worst5:
        if e is None:
            continue
        L.append(f"- {e['sym']} {e['side']} "
                 f"{datetime.fromtimestamp(e['ts_ms']/10**9, tz=timezone.utc):%Y-%m-%d %H:%M}"
                 f" — ret6 {e['ret6']:+.1f} %, MAE 6h {e['mae6']:.1f} %, "
                 f"mult {e['mult']:.1f}×, âge {e['age_h']}h")
    L += [""]

    L += ["## PARTIE 3 — LE JUGEMENT DU RECORD", ""]
    filt_keys = [k2 for k2, (ok, _) in any_pass.items() if ok]
    chosen_filt = None
    if filt_keys:
        # le filtre pré-enregistré : supprimer le pire quartile TRAIN de LA
        # feature qui tient (la première par ordre de pré-enregistrement)
        for key in filt_keys:
            chosen_filt = key
            break
    best_cell = None
    if passing_cells:
        best_cell = max(passing_cells,
                        key=lambda c: cell_stats[c][0]["net_mean"])
    L += [f"- Features qui tiennent la barre (monotone TRAIN+VAL) : "
          + (", ".join(f"`{k2}` ({any_pass[k2][1]})" for k2 in filt_keys)
             or "**aucune**") + ".",
          f"- Cellules d'exit qui passent TRAIN+VAL : "
          + (", ".join(f"h={h}h/thr={t} %" for h, t in passing_cells)
             or "**aucune**") + ".", ""]
    final_ev = events
    if chosen_filt:
        finite = [e for e in events if np.isfinite(e[chosen_filt])]
        tr_fin = [e for e in finite if e["ts_ms"] < cut_ts]
        cuts = [float(q) for q in np.quantile([e[chosen_filt] for e in tr_fin],
                                              [0.25, 0.5, 0.75])]
        lo = cuts[0]
        kept = [e for e in final_ev
                if not (np.isfinite(e[chosen_filt]) and e[chosen_filt] <= lo)]
        dropped = len(final_ev) - len(kept)
        L += [f"- Filtre appliqué : drop du quartile inférieur TRAIN de "
              f"`{chosen_filt}` (≤ {lo:.2f}) → {dropped} events écartés.", ""]
        final_ev = kept
    if best_cell:
        final_ev = with_exit(final_ev, *best_cell)
        L += [f"- Exit appliqué : h={best_cell[0]}h, seuil "
              f"{best_cell[1]:.1f} % (sortie close suivante).", ""]
    res_f = run_wallet(final_ev); res_f["_evs"] = final_ev
    mf = trade_metrics(res_f)
    ftr = [e for e in final_ev if e["ts_ms"] < cut_ts]
    fva = [e for e in final_ev if e["ts_ms"] >= cut_ts]
    rf_tr = run_wallet(ftr); rf_tr["_evs"] = ftr
    rf_va = run_wallet(fva); rf_va["_evs"] = fva
    mf_tr, mf_va = trade_metrics(rf_tr), trade_metrics(rf_va)

    L += ["### BLOC STATS — baseline vs config finale", "",
          f"**Baseline fade 6h inconditionnel :**", ""]
    L += fmt_bloc(bm, months_span)
    gc, gp = guard_fous(base_res)
    L.append(f"- Garde-fous : composé-des-mois {gc*100:.4f} %, somme PnL "
             f"${gp:.4f} — {'OK' if gc < 0.005 and gp < 0.01 else '✗ BUG'}")
    L += ["", f"**Config finale "
          f"(filtre: {chosen_filt or 'aucun'} + exit: "
          f"{f'h={best_cell[0]}h/{best_cell[1]}%' if best_cell else 'aucun'}) :**",
          ""]
    L += fmt_bloc(mf, months_span)
    gc2, gp2 = guard_fous(res_f)
    L.append(f"- Garde-fous : composé-des-mois {gc2*100:.4f} %, somme PnL "
             f"${gp2:.4f} — {'OK' if gc2 < 0.005 and gp2 < 0.01 else '✗ BUG'}")
    L += ["", "**La courbe mensuelle ($, flat 5 %) — baseline | finale :**", "",
          "| Mois | baseline | finale |", "|---|---|---|"]
    mb = {r["month"]: r["pnl"] for r in bm["mrows"]}
    mfin = {r["month"]: r["pnl"] for r in mf["mrows"]}
    for mo in sorted(set(mb) | set(mfin)):
        L.append(f"| {mo} | {mb.get(mo, 0.0):+.2f} | {mfin.get(mo, 0.0):+.2f} |")
    # ——— les 4 trimestres ———
    def quarter_stats(evs: list[dict]) -> dict:
        qmap = {"2025Q4": ("2025-10", "2025-12"), "2026Q1": ("2026-01", "2026-03"),
                "2026Q2": ("2026-04", "2026-06"), "2026Q3": ("2026-07", "2026-09")}
        out = {}
        for q, (a, b) in qmap.items():
            sel = [e for e in evs
                   if a <= datetime.fromtimestamp(e["ts_ms"] / 10**9,
                                                  tz=timezone.utc)
                   .strftime("%Y-%m") <= b]
            if not sel:
                out[q] = (0, float("nan"))
                continue
            r = run_wallet(sel); r["_evs"] = sel
            mm = trade_metrics(r)
            out[q] = (mm.get("n", 0), mm.get("net_mean", float("nan")))
        return out
    L += ["", "**Espérance nette par trimestre (le critère multi-régime) :**",
          "",
          "| Trimestre | baseline n / net % | finale n / net % |",
          "|---|---|---|"]
    qb, qf = quarter_stats(events), quarter_stats(final_ev)
    for q in ("2025Q4", "2026Q1", "2026Q2", "2026Q3"):
        nb, xb = qb[q]
        nf, xf = qf[q]
        L.append(f"| {q} | {nb} / {xb:+.2f} | {nf} / {xf:+.2f} |")
    # ——— le critère du record certain ———
    crit_exp = (mf_tr["net_mean"] > 0 and mf_va["net_mean"] > 0
                and all(np.isfinite(qf[q][1]) and qf[q][1] > 0
                        for q in ("2025Q4", "2026Q1", "2026Q2", "2026Q3")))
    crit_asym = np.isfinite(mf["ratio"]) and mf["ratio"] >= 0.7
    crit_worst = mf["worst"] > -6.0
    L += ["", "**LE CRITÈRE DU RECORD CERTAIN** (pré-enregistré) :", "",
          f"- Espérance nette > 0 sur TRAIN ({mf_tr['net_mean']:+.2f} %) "
          f"ET VAL ({mf_va['net_mean']:+.2f} %) ET les 4 trimestres : "
          f"{'**OUI**' if crit_exp else '**NON**'}",
          f"- Ratio gain/perte ≥ 0,7 : {mf['ratio']:.2f} → "
          f"{'**OUI**' if crit_asym else '**NON**'}",
          f"- Pire trade > -6 % : {mf['worst']:+.2f} % → "
          f"{'**OUI**' if crit_worst else '**NON**'}",
          "",
          f"## VERDICT DU RECORD : "
          f"{'**CERTAIN**' if (crit_exp and crit_asym and crit_worst) else '**PAS ENCORE**'}",
          "",
          "Honnêteté : le forward n=13 reste la confirmation, pas la preuve "
          "(le backtest est la preuve) ; 6 features × 6 cellules = multiple "
          "comparisons, la barre VAL stricte est le garde-fou. Le filtre et "
          "l'exit sont structurellement EX-ANTE (aucune info post-entrée "
          "dans les features ; l'exit lit le prix à h_chk, disponible au "
          "trading réel).",
          "",
          f"Run {(datetime.now(timezone.utc)-t0).total_seconds():.0f} s."]

    out = REPORTS / "fade-loss-anatomy-2026-09-29.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[anat] rapport écrit : {out}")
    print(f"[anat] events={len(events)} train={len(train)} val={len(val)} "
          f"cut={d:%Y-%m-%d %H:%M}")
    print(f"[anat] features qui tiennent : {filt_keys or 'AUCUNE'}")
    print(f"[anat] cellules exit qui passent : {passing_cells or 'AUCUNE'}")
    print(f"[anat] baseline net/trade {bm['net_mean']:+.2f} % ratio "
          f"{bm['ratio']:.2f} pire {bm['worst']:+.2f} % | finale "
          f"{mf['net_mean']:+.2f} % ratio {mf['ratio']:.2f} pire "
          f"{mf['worst']:+.2f} %")
    print(f"[anat] RECORD : {'CERTAIN' if (crit_exp and crit_asym and crit_worst) else 'PAS ENCORE'}")
    return 0


def _mk(res, evs):  # noqa: ARG001 — héritage, non utilisé
    return evs


if __name__ == "__main__":
    raise SystemExit(main())
