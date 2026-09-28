#!/usr/bin/env python3
"""Étude 1 — univers macro/synthétique Aster (28/09) : liquidité, premier
signal de tendance EMA48+slope EMA12, décorrélation BTC/meme, prime mark/index.

Entrée : data/warehouse/klines_macro.db (side-DB, fetcher associé) + lecture
seule de data/warehouse/klines.db pour BTCUSDT/NEIROUSDT (corrélations).
Sortie : rapport console + reports/macro-universe-2026-09-28.md.

Règles harnais respectées : TRAIN/VAL 70/30 PAR LE TEMPS, fees taker 8 bps
round-trip (cf. portfolio_sim.FEE_BPS=4/side), MAE max -> plafond 0-liq
levier <= 100/(maxMAE+0.5), aucun trade inventé, timestamps en ms.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_MACRO = ROOT / "data" / "warehouse" / "klines_macro.db"
DB_MAIN = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "macro-universe-2026-09-28.md"

FEES_BPS_RT = 8.0          # taker 4 bps/side (convention projet)
LIQ_MIN_USD = 1_000_000.0  # volume $ moyen/bougie 1h
MIN_BARS_SIGNAL = 60 * 24  # 60 j minimum pour le signal
HOLD_BARS = 24             # hold 24h
EMA_SLOW, EMA_FAST = 48, 12
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


def ema(vals: list[float], span: int) -> list[float]:
    k = 2.0 / (span + 1)
    out, e = [], vals[0]
    for v in vals:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def load_bars(con: sqlite3.Connection, sym: str) -> list[tuple]:
    return con.execute(
        "SELECT open_time, open, high, low, close, quote_volume, volume"
        " FROM klines WHERE symbol=? AND interval='1h' ORDER BY open_time",
        (sym,)).fetchall()


def signal_trades(bars: list[tuple], sym: str) -> list[dict]:
    """EMA48 +/- slope EMA12 -> entry open t+1, exit open t+1+24, 1x."""
    closes = [b[4] for b in bars]
    if len(bars) < MIN_BARS_SIGNAL + HOLD_BARS + 2:
        return []
    e48 = ema(closes, EMA_SLOW)
    e12 = ema(closes, EMA_FAST)
    trades = []
    n = len(bars)
    for t in range(1, n - HOLD_BARS - 1):
        c, s48, s12 = closes[t], e48[t], e12[t]
        slope = e12[t] - e12[t - 1]
        d = 1 if (c > s48 and slope > 0) else (-1 if (c < s48 and slope < 0) else 0)
        if d == 0:
            continue
        entry = bars[t + 1][1]
        exit_ = bars[t + 1 + HOLD_BARS][1]
        if entry <= 0 or exit_ <= 0:
            continue
        lo = min(bars[i][3] for i in range(t + 1, t + 2 + HOLD_BARS))
        hi = max(bars[i][2] for i in range(t + 1, t + 2 + HOLD_BARS))
        gross = (exit_ / entry - 1) * 100 * d
        net = gross - FEES_BPS_RT / 100.0 * 1  # bps -> %
        mae = ((entry - lo) / entry * 100) if d == 1 else ((hi - entry) / entry * 100)
        mae = max(mae, 0.0)
        trades.append({"sym": sym, "dir": d, "entry_ts": bars[t + 1][0],
                       "exit_ts": bars[t + 1 + HOLD_BARS][0],
                       "net": net, "mae": mae, "win": net > 0})
    return trades


def split_tv(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    if len(trades) < 6:
        return trades, []
    trades = sorted(trades, key=lambda x: x["entry_ts"])
    k = int(len(trades) * 0.7)
    return trades[:k], trades[k:]


def stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "wr": 0.0, "exp": 0.0, "mae_max": 0.0}
    w = sum(1 for t in trades if t["win"])
    return {"n": len(trades), "wr": 100.0 * w / len(trades),
            "exp": sum(t["net"] for t in trades) / len(trades),
            "mae_max": max(t["mae"] for t in trades)}


def daily_returns(bars: list[tuple]) -> dict[str, float]:
    by_day: dict[str, float] = {}
    for b in bars:
        day = datetime.fromtimestamp(b[0] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        by_day[day] = b[4]  # dernier close du jour
    days = sorted(by_day)
    return {days[i]: by_day[days[i]] / by_day[days[i - 1]] - 1
            for i in range(1, len(days))}


def pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 20:
        return float("nan")
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a) ** 0.5
    vb = sum((y - mb) ** 2 for y in b) ** 0.5
    return cov / (va * vb) if va > 0 and vb > 0 else float("nan")


def monthly_block(trades: list[dict]) -> list[tuple]:
    per: dict[str, list[float]] = {}
    for t in trades:
        m = datetime.fromtimestamp(t["exit_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")
        per.setdefault(m, []).append(t["net"])
    return sorted(per.items())


def main() -> int:
    con = sqlite3.connect(f"file:{DB_MACRO}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout=30000")
    syms = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' ORDER BY symbol")]
    src = sqlite3.connect(f"file:{DB_MAIN}?mode=ro", uri=True)

    # ---- 1) couverture + 2) liquidité ----
    rows, liq_ok = [], []
    for s in syms:
        bars = load_bars(con, s)
        gaps = sum(1 for i in range(1, len(bars))
                   if bars[i][0] - bars[i - 1][0] > 3_600_000)
        qv = [b[5] if b[5] else b[4] * b[6] for b in bars]
        avg_qv = sum(qv) / len(qv) if qv else 0.0
        med_qv = sorted(qv)[len(qv) // 2] if qv else 0.0
        days = (bars[-1][0] - bars[0][0]) / 86_400_000 if bars else 0.0
        ok = avg_qv >= LIQ_MIN_USD and days >= 60
        liq_ok.append(s) if ok else None
        rows.append({"sym": s, "n": len(bars), "days": days, "gaps": gaps,
                     "avg_qv": avg_qv, "med_qv": med_qv, "ok": ok})
    # tier indicatif : la liquidite 1 M$ a tue tout le monde -> on signale
    # quand meme sur les symboles >= 60 j (>= 100 k$/bougie = 2e seuil parlant)
    INDIC_MIN_USD = 100_000.0
    indic = [r["sym"] for r in rows
             if r["days"] >= 60 and r["avg_qv"] >= INDIC_MIN_USD]

    # ---- 3) signal tendance ----
    all_trades: dict[str, list[dict]] = {}
    for s in (liq_ok or indic):
        tr = signal_trades(load_bars(con, s), s)
        if tr:
            all_trades[s] = tr
    sig_rows = []
    for s, tr in all_trades.items():
        trn, val = split_tv(tr)
        st, sv = stats(trn), stats(val)
        mae_all = max((t["mae"] for t in tr), default=0.0)
        lev_cap = 100.0 / (mae_all + 0.5) if mae_all > 0 else 200.0
        sig_rows.append({"sym": s, "train": st, "val": sv, "n_all": len(tr),
                         "mae_max": mae_all, "lev_cap": min(lev_cap, 20.0),
                         "trades": tr})

    # ---- 4) décorrélation ----
    btc = daily_returns(load_bars(src, "BTCUSDT"))
    nei = daily_returns(load_bars(src, "NEIROUSDT"))
    corr_rows = []
    for r in rows:
        dr = daily_returns(load_bars(con, r["sym"]))
        common_b = sorted(set(dr) & set(btc))
        common_n = sorted(set(dr) & set(nei))
        cb = pearson([dr[d] for d in common_b], [btc[d] for d in common_b])
        cn = pearson([dr[d] for d in common_n], [nei[d] for d in common_n])
        corr_rows.append({"sym": r["sym"], "btc": cb, "neiro": cn,
                          "n_b": len(common_b), "n_n": len(common_n)})

    # ---- 5) prime mark/index top 5 liquidité (one-shot) ----
    top5 = [r["sym"] for r in sorted(rows, key=lambda x: -x["avg_qv"])[:5]]
    prem = []
    now_ms = int(time.time() * 1000)
    wcon = sqlite3.connect(str(DB_MACRO), timeout=30)
    wcon.execute("PRAGMA busy_timeout=30000")
    wcon.execute("""CREATE TABLE IF NOT EXISTS premium_history (
        symbol TEXT, mark_price REAL, index_price REAL, premium_pct REAL,
        last_funding_rate REAL, next_funding_time_ms INTEGER,
        captured_at_ms INTEGER, PRIMARY KEY (symbol, captured_at_ms))""")
    for s in top5:
        try:
            req = urllib.request.Request(
                f"https://fapi.asterdex.com/fapi/v1/premiumIndex?symbol={s}",
                headers={"user-agent": UA})
            with urllib.request.urlopen(req, timeout=15) as rh:
                d = json.load(rh)
            mark, idx = float(d["markPrice"]), float(d["indexPrice"])
            p = (mark / idx - 1) * 100 if idx else 0.0
            wcon.execute("INSERT OR IGNORE INTO premium_history VALUES (?,?,?,?,?,?,?)",
                         (s, mark, idx, round(p, 6), float(d["lastFundingRate"]),
                          int(d["nextFundingTime"]), now_ms))
            wcon.commit()
            prem.append({"sym": s, "prem": p, "funding": float(d["lastFundingRate"]) * 100})
        except Exception as e:
            prem.append({"sym": s, "prem": None, "funding": None, "err": str(e)})
    wcon.close()
    con.close()
    src.close()

    # ---- BLOC STATS mensuel (composite égal-pondéré des trades liquides) ----
    flat = [t for r in sig_rows for t in r["trades"]]
    per = monthly_block(flat)
    monthly, eq, peak, maxdd = [], 1.0, 1.0, 0.0
    for m, rets in per:
        n = len(rets)
        wr = 100.0 * sum(1 for x in rets if x > 0) / n
        # taille par trade = 1/n_trades_du_mois (wallet fictif séquentiel mensuel)
        mret = sum(x / n for x in rets) * 100  # % du wallet
        eq *= (1 + mret / 100)
        peak = max(peak, eq)
        maxdd = max(maxdd, 1 - eq / peak)
        monthly.append((m, n, wr, mret))

    # ---- rapport ----
    L = []
    L.append("# Étude 1 — Univers macro/synthétique Aster (2026-09-28)\n")
    L.append("Source : fapi.asterdex.com (587 perps) -> side-DB `data/warehouse/klines_macro.db`, 1h.")
    L.append("Fees taker 8 bps RT. TRAIN/VAL 70/30 par le temps. 1x, hold 24h, signal = EMA48 + slope EMA12.\n")
    L.append("## 1) Couverture & 2) Liquidité (seuil stats : 1 M$/bougie 1h, >= 60 j)\n")
    L.append("| symbole | bougies | jours | trous | vol$ moyen | vol$ median | stats |")
    L.append("|---|---|---|---|---|---|---|")
    for r in rows:
        L.append(f"| {r['sym']} | {r['n']} | {r['days']:.0f} | {r['gaps']} | "
                 f"{r['avg_qv']/1e6:.2f} M | {r['med_qv']/1e6:.2f} M | "
                 f"{'OUI' if r['ok'] else 'ecarte'} |")
    L.append("\n## 3) Signal tendance (TRAIN -> VAL, par symbole)\n")
    L.append("| symbole | n | WR tr | exp tr % | WR val | exp val % | MAE max % | lev cap 0-liq |")
    L.append("|---|---|---|---|---|---|---|---|")
    for s in sig_rows:
        v = s["val"]
        L.append(f"| {s['sym']} | {s['n_all']} | {s['train']['wr']:.0f} | "
                 f"{s['train']['exp']:+.3f} | {v['wr']:.0f} ({v['n']}) | "
                 f"{v['exp']:+.3f} | {s['mae_max']:.2f} | {s['lev_cap']:.1f}x |")
    L.append("\n## 4) Décorrélation (rendements quotidiens vs BTC vs NEIRO)\n")
    L.append("| symbole | corr BTC | corr NEIRO | n jours communs |")
    L.append("|---|---|---|---|")
    for c in sorted(corr_rows, key=lambda x: abs(x["btc"]) if x["btc"] == x["btc"] else 9):
        L.append(f"| {c['sym']} | {c['btc']:+.2f} | {c['neiro']:+.2f} | {c['n_b']} |")
    L.append("\n## 5) Prime mark/index (snapshot one-shot, top 5 liquidité)\n")
    L.append("| symbole | prime % | funding ann. approx % |")
    L.append("|---|---|---|")
    for p in prem:
        fp = p["funding"] * 3 * 365 if p["funding"] is not None else None  # /8h -> /an
        L.append(f"| {p['sym']} | {p['prem']:+.4f} | {fp:+.1f} |" if p["prem"] is not None
                 else f"| {p['sym']} | ERR | - |")
    L.append("\n## BLOC STATS mensuel — composite indicatif (tier >= 100 k$/bougie, "
             "AUCUN symbole >= 1 M$ : ce bloc n'est PAS tradable en taille)\n")
    L.append("| mois | trades | WR % | ROI mois % |")
    L.append("|---|---|---|---|")
    for m, n, wr, mret in monthly:
        L.append(f"| {m} | {n} | {wr:.0f} | {mret:+.2f} |")
    neg = sum(1 for _, _, _, r in monthly if r < 0)
    best = max(monthly, key=lambda x: x[3], default=None)
    worst = min(monthly, key=lambda x: x[3], default=None)
    L.append(f"\n- wallet composite : x{eq:.3f} ({(eq-1)*100:+.1f}%), DD max {maxdd*100:.1f}%")
    if best and worst:
        L.append(f"- meilleur mois {best[0]} {best[3]:+.2f}% | pire {worst[0]} {worst[3]:+.2f}% | mois negatifs {neg}/{len(monthly)}")
    L.append("- garde-fou compose-des-mois : le ROI compose ci-dessus fait foi sur le cumul simple.\n")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nrapport -> {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
