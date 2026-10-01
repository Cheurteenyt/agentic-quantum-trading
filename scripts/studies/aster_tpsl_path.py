#!/usr/bin/env .venv/bin/python
"""T23 — Simulation TP/SL PATH bar-par-bar sur les trades réels (paper_trades klines.db).

Question : un TP/SL aurait-il fait mieux que le hold pur sur les trades réels
(v5 + machine) ? Grille tp x sl, PnL composé, WR, DD, split TRAIN/VAL 70/30.

Méthode :
- trades : paper_trades status='closed' avec entry/exit/ts cohérents (READ-ONLY).
- path   : barres 1h de klines (open_time >= entry_ts, < exit_ts), par trade.
- long  : TP si high >= E*(1+tp) ; SL si low  <= E*(1-sl).
- short : TP si low  <= E*(1-tp) ; SL si high >= E*(1+sl).
- AMBIGUÏTÉ (TP et SL touchés dans la MÊME barre 1h) : SL d'abord (conservatif).
- la barre d'entry compte entière (entry au open de la barre).
- PnL en % prix brut : TP=+tp, SL=-sl, hold=d*(X/E-1)*100. Les fees/funding
  (bruit ~±0,1-0,2pt dans ret_pct de la DB) sont identiques pour toutes les
  configs (exactement 1 exit par trade quel que soit le config) -> comparaison non biaisée.
- témoin tp=inf/sl=inf = hold pur (reproduction du réel, prix bruts).
- split TRAIN/VAL PAR LE TEMPS 70/30 : bord = quantile 70% des entry_ts.
  (NB : le bord 2025-06 du cahier des charges précède toutes les données —
  les trades réels vont du 2026-09-22 au 2026-10-01 — donc split 70/30 doctrine.)

Usage :
  .venv/bin/python scripts/studies/aster_tpsl_path.py               # grille complète + TRAIN/VAL
  .venv/bin/python scripts/studies/aster_tpsl_path.py --tp 3 --sl 2 # config unique détaillée
  .venv/bin/python scripts/studies/aster_tpsl_path.py --source data/warehouse/klines.db
"""
import argparse
import math
import sqlite3
import sys
from datetime import datetime, timezone

TP_GRID = [1.0, 2.0, 3.0, 5.0, 8.0, math.inf]
SL_GRID = [1.0, 2.0, 3.0, 5.0, math.inf]


def fmt_ts(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def load_trades(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT signal, symbol, horizon_h, direction, entry_ts, entry_price, "
        "exit_ts, exit_price, ret_pct FROM paper_trades "
        "WHERE status='closed' AND entry_ts IS NOT NULL AND exit_ts IS NOT NULL "
        "AND entry_price > 0 AND exit_price > 0 AND exit_ts > entry_ts"
    ).fetchall()
    bars = {}
    symbols = sorted({r[1] for r in rows})
    for sym in symbols:
        bars[sym] = cur.execute(
            "SELECT open_time, high, low FROM klines "
            "WHERE symbol=? AND interval='1h' ORDER BY open_time", (sym,)
        ).fetchall()
    con.close()
    trades = []
    for sig, sym, hor, d, ets, ep, xts, xp, ret in rows:
        bl = bars[sym]
        trades.append({
            "signal": sig, "symbol": sym, "horizon": hor, "d": d,
            "ets": ets, "ep": ep, "xts": xts, "xp": xp, "ret": ret,
            "family": "machine" if sig.startswith("machine_") else "v5",
            "_bars": bl,
        })
    return trades


def trade_bars(t):
    bl = t["_bars"]
    ts = [b[0] for b in bl]
    import bisect
    i0 = bisect.bisect_left(ts, t["ets"])
    i1 = bisect.bisect_left(ts, t["xts"])
    return bl[i0:i1]


def simulate(trades, tp, sl):
    """Retourne liste de dicts outcome par trade (ordre d'entrée conservé)."""
    out = []
    for t in trades:
        d, E, X = t["d"], t["ep"], t["xp"]
        hold_pnl = d * (X / E - 1.0) * 100.0
        pnl, kind, touched_bar = hold_pnl, "hold", None
        bars = trade_bars(t)
        covered_h = sum(1 for _ in bars)
        want_h = max(1.0, (t["xts"] - t["ets"]) / 3600000.0)
        partial = covered_h < want_h * 0.9
        for k, (_, hi, lo) in enumerate(bars):
            if d == 1:   # long
                hit_tp = hi >= E * (1 + tp / 100.0)
                hit_sl = lo <= E * (1 - sl / 100.0)
            else:        # short
                hit_tp = lo <= E * (1 - tp / 100.0)
                hit_sl = hi >= E * (1 + sl / 100.0)
            if hit_sl:               # RÈGLE D'AMBIGUÏTÉ : SL d'abord (conservatif)
                pnl, kind, touched_bar = -sl, "SL", k
                break
            if hit_tp:
                pnl, kind, touched_bar = +tp, "TP", k
                break
        out.append({**t, "pnl": pnl, "kind": kind, "hold_pnl": hold_pnl,
                    "partial": partial, "touched_bar": touched_bar})
    return out


def stats(outs):
    """PnL composé, WR, DD (courbe composée ordonnée par entry_ts), mix sorties."""
    outs = sorted(outs, key=lambda o: o["ets"])
    eq, peak, dd = 1.0, 1.0, 0.0
    ntp = nsl = nho = 0
    wins = 0
    for o in outs:
        eq *= (1 + o["pnl"] / 100.0)
        peak = max(peak, eq)
        dd = max(dd, (peak - eq) / peak * 100.0)
        ntp += o["kind"] == "TP"
        nsl += o["kind"] == "SL"
        nho += o["kind"] == "hold"
        wins += o["pnl"] > 0
    n = len(outs)
    return {
        "n": n, "eq": eq, "dd": dd, "wr": wins / n * 100 if n else 0.0,
        "pct_tp": ntp / n * 100 if n else 0.0,
        "pct_sl": nsl / n * 100 if n else 0.0,
        "pct_hold": nho / n * 100 if n else 0.0,
        "exp": sum(o["pnl"] for o in outs) / n if n else 0.0,
        "eqdd": eq / dd if dd > 1e-9 else math.inf,
    }


def filter_outs(outs, **kw):
    res = outs
    for key, val in kw.items():
        res = [o for o in res if o[key] == val]
    return res


def row_line(name, s):
    return (f"| {name} | {s['n']} | {s['eq']*100-100:+.1f}% | {s['dd']:.1f}% | "
            f"{s['eqdd']:.2f} | {s['wr']:.1f}% | {s['exp']:+.2f}% | "
            f"{s['pct_tp']:.0f}% | {s['pct_sl']:.0f}% | {s['pct_hold']:.0f}% |")


HDR = ("| config | n | PnL comp | DD | eq/DD | WR | exp/trade | TP% | SL% | hold% |\n"
       "|---|---|---|---|---|---|---|---|---|---|")


def tpsl_name(tp, sl):
    tp_s = "inf" if math.isinf(tp) else f"{tp:g}"
    sl_s = "inf" if math.isinf(sl) else f"{sl:g}"
    return f"tp={tp_s}/sl={sl_s}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/warehouse/klines.db")
    ap.add_argument("--tp", type=float, default=None)
    ap.add_argument("--sl", type=float, default=None)
    args = ap.parse_args()

    trades = load_trades(args.source)
    # couverture barres
    n_partial = sum(1 for t in trades if len(trade_bars(t)) < max(1.0, (t["xts"] - t["ets"]) / 3600000.0) * 0.9)
    n_zero = sum(1 for t in trades if not trade_bars(t))
    ets_all = sorted(t["ets"] for t in trades)
    boundary = ets_all[int(0.7 * len(ets_all))]

    print(f"DB: {args.source}")
    print(f"trades éligibles: n={len(trades)} | symbols={len({t['symbol'] for t in trades})} | "
          f"long={sum(1 for t in trades if t['d']==1)} short={sum(1 for t in trades if t['d']==-1)} | "
          f"v5={sum(1 for t in trades if t['family']=='v5')} machine={sum(1 for t in trades if t['family']=='machine')}")
    print(f"couverture barres 1h: sans barres={n_zero}, couverture <90% (fallback hold)={n_partial}")
    print(f"fenêtre: {fmt_ts(ets_all[0])} -> {fmt_ts(ets_all[-1])} (entry)")
    print(f"split TRAIN/VAL 70/30 par le temps: bord = {fmt_ts(boundary)} | "
          f"TRAIN={sum(1 for x in ets_all if x < boundary)} VAL={sum(1 for x in ets_all if x >= boundary)}")

    if args.tp is not None and args.sl is not None:
        outs = simulate(trades, args.tp, args.sl)
        print(f"\n=== config tp={args.tp:g}% sl={args.sl:g}% : détail par trade ===")
        print("signal | symbol | dir | outcome | pnl | hold_pnl | delta")
        for o in sorted(outs, key=lambda o: o["ets"]):
            print(f"{o['signal']} | {o['symbol']} | {'L' if o['d']==1 else 'S'} | "
                  f"{o['kind']} | {o['pnl']:+.2f} | {o['hold_pnl']:+.2f} | {o['pnl']-o['hold_pnl']:+.2f}")
        print()
        for name, sel in [("GLOBAL", outs), ("TRAIN", [o for o in outs if o['ets'] < boundary]),
                          ("VAL", [o for o in outs if o['ets'] >= boundary]),
                          ("long", filter_outs(outs, d=1)), ("short", filter_outs(outs, d=-1)),
                          ("v5", filter_outs(outs, family='v5')), ("machine", filter_outs(outs, family='machine'))]:
            s = stats(sel) if sel else None
            print(f"{name}: n={s['n'] if s else 0}" + (f" | PnL comp {s['eq']*100-100:+.1f}% | DD {s['dd']:.1f}% | WR {s['wr']:.1f}% | TP% {s['pct_tp']:.0f} SL% {s['pct_sl']:.0f} hold% {s['pct_hold']:.0f}" if s else ""))
        return

    # grille complète
    print(f"\n{HDR}")
    grid = []
    for tp in TP_GRID:
        for sl in SL_GRID:
            outs = simulate(trades, tp, sl)
            s = stats(outs)
            grid.append((tp, sl, s, outs))
            print(row_line(tpsl_name(tp, sl), s))

    # TRAIN/VAL par config
    print(f"\n=== TRAIN (entry < {fmt_ts(boundary)}) ===\n{HDR}")
    train_stats = {}
    for tp, sl, _, _ in grid:
        outs = simulate(trades, tp, sl)
        st = stats([o for o in outs if o["ets"] < boundary])
        train_stats[(tp, sl)] = st
        print(row_line(tpsl_name(tp, sl), st))

    print(f"\n=== VAL (entry >= {fmt_ts(boundary)}) ===\n{HDR}")
    val_stats = {}
    for tp, sl, _, _ in grid:
        outs = simulate(trades, tp, sl)
        st = stats([o for o in outs if o["ets"] >= boundary])
        val_stats[(tp, sl)] = st
        print(row_line(tpsl_name(tp, sl), st))

    # élection TRAIN -> contrôle VAL (discipline : choix sur TRAIN uniquement)
    def score(s):
        return s["eqdd"] if math.isfinite(s["eqdd"]) else s["eq"] * 1e6
    best_train = max(train_stats, key=lambda k: score(train_stats[k]))
    witness = (math.inf, math.inf)
    print(f"\nmeilleure config TRAIN (par eq/DD): tp={best_train[0]:g} sl={best_train[1]:g}")
    print(f"  TRAIN: {row_line(tpsl_name(*best_train), train_stats[best_train])}")
    print(f"  VAL  : {row_line(tpsl_name(*best_train), val_stats[best_train])}")
    print(f"témoin hold pur:")
    print(f"  TRAIN: {row_line('hold', train_stats[witness])}")
    print(f"  VAL  : {row_line('hold', val_stats[witness])}")

    # multiplicité déclarée
    print(f"\nmultiplicité: {len(TP_GRID)*len(SL_GRID)} configs testées -> risque de surajustement déclaré;")
    print("seule une config qui bat le hold en TRAIN ET en VAL mérite le statut CANDIDAT.")


if __name__ == "__main__":
    sys.exit(main())
