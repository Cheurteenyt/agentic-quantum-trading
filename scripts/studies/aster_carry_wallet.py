#!/usr/bin/env python
"""T22 — TEST DU WALLET SÉQUENTIEL du carry de funding T21 (porte de promotion).

Recharge les trades du one-shot T21 (`scripts/studies/aster_discovery_2123.py`,
config `carry_thr-0.5+2.0_h48`, funding RÉEL cache reports/) et les passe à
la porte obligatoire : `scripts.stacked_portfolio.run_stack` (IMPORTÉ, non
modifié) — wallet composé $100, un slot par stratégie, liq en chemin
(MAE ≥ 100/lev − 0,5), marge % de la balance.

TROIS ÉCARTS T21 vs harnais, découverts et quantifiés ici (anti-boucle) :
  1. UNITÉ FUNDING ×8 : le moteur T21 somme le taux ffillé sur CHAQUE barre
     horaire alors que les events Aster sont espacés de 8 h (médiane 8,00 h
     dans le cache) → PnL funding surcompté ×8.
  2. DÉNOMINATION SHORT : T21 calcule le gross short en (entry/exit − 1)
     (dénominé SORTIE) ; le harnais (stacked_portfolio, the_machine) en
     (entry − exit)/entry (dénominé ENTRÉE = économie réelle d'un short).
     Sur les gros stops (5×ATR en crash), l'écart est massif.
  3. SOUS-ENSEMBLE SÉRIALISÉ : le slot unique du wallet saute les signaux
     groupés (crash = funding extrême sur les 3 majeures à la fois) — or
     c'est LÀ que vit le carry.
Conventions comparées (sommes cumulées % notionnel, 999 trades) :
  ASIS   = T21 tel quel (unité ×8 + short-sortie) : +1085 %
  T21-ex = T21 avec funding exact (short-sortie)  : +102 %
  HARNAIS= funding exact + short-entrée (économie réelle) : −28 %
Le verdict repose sur HARNAIS (celui du wallet) ; les deux autres mesurent
les artefacts. DB en READ-ONLY. Écrit uniquement reports/aster_carry_wallet.md.
  .venv/bin/python scripts/studies/aster_carry_wallet.py
"""
from __future__ import annotations

import bisect
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

STUDIES_DIR = Path(__file__).resolve().parent
ROOT = STUDIES_DIR.parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAJORS, btc_regime_series, monthly_rows)
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, TAKER_RT, MAKER_RT, funding_hourly_all, run_stack)
from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.studies.aster_discovery_2123 import (  # noqa: E402
    COST_RT, CONFIGS, DB_PATH, FUND_CACHE, SYMBOLS, build_signals, load_klines,
    run as run_t21)

REPORT = ROOT / "reports" / "aster_carry_wallet.md"
CFG_NAME = "carry_thr-0.5+2.0_h48"
FEE_RT_BPS = COST_RT * 1e4          # 8 bps aller-retour sur le notionnel
MARGIN = 0.10                       # marge fixe 10 % de la balance (convention)
LEVS = (1.0, 1.5, 2.1)              # 2.1 = cap 0-liq (maxMAE 46.1 % -> 100/46.6)
VAL_START_MS = 1704067200000        # 2024-01-01 (split T21 TRAIN/VAL)
K_MACHINE = 0.89                    # calibration machine (T8), copiée telle quelle


def log(m: str) -> None:
    print(m, flush=True)


# ------------------------------------------------------------------ reload T21
def load_carry_trades() -> list[dict]:
    """Rejoue EXACTEMENT le moteur T21 (assert trade-par-trade contre run())
    et exporte la décomposition : prix (gross T21), funding ASIS (×8),
    funding EXACT (event 8h ×1), mae, durée."""
    name, fam, p = next(c for c in CONFIGS if c[0] == CFG_NAME)
    fund = json.loads(FUND_CACHE.read_text())
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    trades: list[dict] = []
    for s in SYMBOLS:
        df = load_klines(con, s)
        ff = pd.DataFrame(fund[s], columns=["t", "rate"])
        ff["rate"] = ff["rate"] * 1e4                      # bps/8h (comme T21)
        sig = build_signals(df, fam, p, ff)
        ref = run_t21(df, sig)                             # vérité T21
        ev_ts = np.array([e[0] for e in fund[s]])
        ev_rt = np.array([e[1] for e in fund[s]])          # taux décimaux /8h
        n = len(df)
        o, h, l = df["open"].values, df["high"].values, df["low"].values
        hold, stop_atr = sig["hold"], sig["stop_atr"]
        atrv, fundv, ts_all = sig["atr"], sig["fund_bps8h"], df["ts"].values
        pos, entry_px, stop, entry_i = 0, 0.0, 0.0, 0
        k = 0
        for i in range(1, n - 1):
            if pos == 0:
                if sig["long"][i] and np.isfinite(atrv[i]):
                    pos, entry_px, entry_i = 1, o[i + 1], i + 1
                    stop = entry_px - stop_atr * atrv[i]
                elif sig["short"][i] and np.isfinite(atrv[i]):
                    pos, entry_px, entry_i = -1, o[i + 1], i + 1
                    stop = entry_px + stop_atr * atrv[i]
                continue
            exit_px = None
            if pos == 1 and l[i] <= stop:
                exit_px = stop
            elif pos == -1 and h[i] >= stop:
                exit_px = stop
            elif i - entry_i >= (hold or 10**9):
                exit_px = o[i + 1]
            if exit_px is None:
                continue
            gross_t21 = (exit_px / entry_px - 1) if pos == 1 else (entry_px / exit_px - 1)
            gross_har = pos * (exit_px / entry_px - 1) * 100   # dénominé ENTRÉE (harnais)
            fs = fundv[entry_i:i + 1].sum()                # somme bps/8h ffillée
            dur_h = i + 1 - entry_i
            e_ts = int(ts_all[entry_i])
            x_ts = e_ts + dur_h * 3600_000
            lo = bisect.bisect_left(ev_ts, e_ts)
            hi = bisect.bisect_right(ev_ts, x_ts)
            f_asis = -pos * fs / 100.0                     # % notionnel, T21 tel quel
            f_exact = -pos * ev_rt[lo:hi].sum() * 100.0    # % notionnel, exact 8h
            if pos == 1:
                mae = max(0.0, (1 - min(l[entry_i:i + 1]) / entry_px) * 100)
            else:
                mae = max(0.0, (max(h[entry_i:i + 1]) / entry_px - 1) * 100)
            ret_asis = gross_t21 * 100 - COST_RT * 100 + f_asis
            assert abs(ret_asis - ref[k]["ret"]) < 1e-9 and ref[k]["dir"] == pos, \
                f"[reload] divergence moteur vs T21 sur {s} trade #{k}"
            trades.append({"sym": s, "ts": e_ts, "dir": pos, "entry": float(entry_px),
                           "exit": float(exit_px), "gross": gross_t21 * 100,
                           "gross_har": gross_har, "mae": mae,
                           "dur_h": dur_h, "f_asis": f_asis, "f_exact": f_exact})
            pos, k = 0, k + 1
    con.close()
    trades.sort(key=lambda t: t["ts"])
    return trades


def to_events(trades: list[dict], conv: str, lev: float,
              key: str | None = None) -> tuple[list[dict], dict]:
    """Trades -> events run_stack en économie HARNAIS : prix short dénominé
    ENTRÉE, funding exact par trade via clé synthétique (run_stack indexe
    funding_hourly par e['sym']). ATTENTION au signe : run_stack attend le
    taux de MARCHÉ signé (positif = les longs paient) tandis que
    fund_pct = ce que LA POSITION reçoit = −dir × marché :
      fh[clé] = (−fund_pct / dir) / dur_h  =>  fund_sign=−dir reproduit le PnL.
    frais = 8 bps RT via fee_rt_bps. ts_ms en NANOSECONDES (harnais)."""
    fh: dict[str, float] = {}
    events = []
    for k, t in enumerate(trades):
        kkey = key if key is not None else f"{t['sym']}#{k:05d}"   # ne JAMAIS muter key
        fund_pct = t["f_asis"] if conv == "ASIS" else t["f_exact"]
        fh[kkey] = -fund_pct / (t["dir"] * t["dur_h"])     # %/h MARCHÉ sur la fenêtre
        price_ret_short = t["dir"] * (t["exit"] / t["entry"] - 1) * 100
        events.append({"sym": kkey, "ts_ms": t["ts"] * 10**6, "strategy": "carry",
                       "lev": lev, "hold_h": t["dur_h"], "fee_rt_bps": FEE_RT_BPS,
                       "entry": t["entry"], "price_ret_short": price_ret_short,
                       "mae_adverse": t["mae"], "fund_sign": -t["dir"]})
    return events, fh


# ------------------------------------------------------------------ bloc stats
def bloc(res: dict, n_offered: int, capital: float, label: str) -> tuple[list[str], list, float, float]:
    n = max(res["n"], 1)
    years = np.nan
    if res["trades"]:
        t0 = min(t["entry_ts"] for t in res["trades"])
        t1 = max(t["exit_ts"] for t in res["trades"])
        years = (t1 - t0).total_seconds() / (365.25 * 86400)
    final = res["balance"]
    cagr = ((final / capital) ** (1 / years) - 1) * 100 if years and years > 0 else np.nan
    mr = monthly_rows(res["trades"], capital)
    rois = [r["roi"] for r in mr]
    prod, sum_pnl = 1.0, 0.0
    for r in mr:
        prod *= 1 + r["roi"] / 100
        sum_pnl += r["pnl"]
    gap_c = abs(prod - final / capital)
    gap_p = abs(sum_pnl - (final - capital))
    pnls = [t["pnl"] for t in res["trades"]]
    expo = (sum((t["exit_ts"] - t["entry_ts"]).total_seconds() for t in res["trades"])
            / (years * 365.25 * 86400) * 100) if years else 0.0
    lines = [
        f"**{label}** : ${capital:,.0f} → **${final:,.2f}** "
        f"(ROI total {(final / capital - 1) * 100:+.1f} %, "
        f"ROI/an {cagr:+.1f} %, DD {res['max_dd']:.1f} %)",
        f"  {res['n']}/{n_offered} trades pris, WR {res['n_wins'] / n * 100:.1f} %, "
        f"liq {res['n_liq']}, frais ${res['fees']:,.2f}, funding ${res['funding']:+,.2f}",
        f"  mois : {sum(1 for x in rois if x > 0)}+ / {sum(1 for x in rois if x < 0)}− "
        f"(record {max(rois):+.1f} %, pire {min(rois):+.1f} %)"
        if rois else "  aucun trade",
        f"  espérance ${np.mean(pnls):+.3f}/trade, exposition ~{expo:.0f} % du temps"
        if pnls else "",
        f"  garde-fous : composé-des-mois écart {gap_c * 100:.3f} % "
        f"{'OK' if gap_c < 0.005 else 'BUG'} · somme-PnL écart ${gap_p:.4f} "
        f"{'OK' if gap_p < 0.01 else 'BUG'}",
    ]
    return [x for x in lines if x], mr, gap_c, gap_p


def run_wallet(trades: list[dict], conv: str, lev: float, label: str,
               slots: int = 1) -> dict:
    if slots == 1:
        events, fh = to_events(trades, conv, lev)
        res = run_stack(events, CAPITAL, lambda e: MARGIN, fh)
    else:
        events, fh = [], {}
        for k, t in enumerate(trades):          # index GLOBAL : clés fh uniques
            sub, sub_fh = to_events([t], conv, lev, key=f"{t['sym']}#{k:05d}")
            sub[0]["strategy"] = f"carry_{t['sym']}"
            events += sub
            fh.update(sub_fh)
        events.sort(key=lambda e: e["ts_ms"])
        res = run_stack(events, CAPITAL, lambda e: MARGIN, fh)
    lines, mr, gap_c, gap_p = bloc(res, len(trades), CAPITAL, label)
    return {"res": res, "lines": lines, "mr": mr, "gap_c": gap_c, "gap_p": gap_p}


# ------------------------------------------------- replay machine (corrélation)
def replay_machine() -> dict[str, dict]:
    """Rejoue les 4 flux machine (sizing canonique copié de the_machine.main)
    et le stack complet. AUCUNE écriture (con ro, mae_state non touché)."""
    from scripts.the_machine import collect_meme  # noqa: E402
    from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402

    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    log("[machine] collect_featured majors...")
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = 10
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan")) for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    med_majors = float(np.median([e["atr_pct"] for e in gated]))

    log("[machine] funding_history...")
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    funding_ts: dict[str, tuple[list, list]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = funding_ts.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)   # leçon ts_ms : unité !
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    for e in gated:
        ranks, own = [], np.nan
        for s in MAJORS:
            ft = funding_ts.get(s)
            if not ft or len(ft[0]) < 5:
                continue
            pos = int(np.searchsorted(np.array(ft[0]), e["ts_ms"], side="right")) - 1
            if pos < 0:
                continue
            if s == e["sym"]:
                own = ft[1][pos]
            ranks.append(ft[1][pos])
        e["fund_rank"] = (float(np.mean(np.array(ranks) <= own))
                          if ranks and np.isfinite(own) else np.nan)

    log("[machine] cascade_meme...")
    meme = collect_meme(con)
    mae_meme = max(e["mae_adverse"] for e in meme)
    lev_meme = max(1, int(100 / (mae_meme + 0.5)))
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = lev_meme

    log("[machine] survivor...")
    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
        e.setdefault("hold_h", 72)

    log("[machine] vol_spike...")
    from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
    spike = collect_vol_spike(con, hold=6)
    med_spike = float(np.median([e["atr_pct"] for e in spike])) if spike else np.nan
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
        e.setdefault("hold_h", 6)
    con.close()

    def machine_fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * K_MACHINE * (e["atr_pct"] / med_majors), 0.08 * K_MACHINE),
                     0.40 * K_MACHINE)
            if (np.isfinite(e.get("fund_rank", np.nan)) and e["fund_rank"] <= 0.33):
                return min(s0 * 1.5, 0.50 * K_MACHINE)
            return s0
        if s == "cascade_meme":
            return min(max(0.10 * K_MACHINE * (e["atr_pct"] / med_meme), 0.02 * K_MACHINE),
                       0.30 * K_MACHINE)
        if s == "vol_spike_6h":
            return min(max(0.10 * K_MACHINE * (e["atr_pct"] / med_spike), 0.02 * K_MACHINE),
                       0.30 * K_MACHINE)
        return 0.20 * K_MACHINE

    flux = {"cascade_majors": gated, "cascade_meme": meme,
            "survivor": surv, "vol_spike": spike}
    out = {}
    for nm, evs in flux.items():
        evs = sorted(evs, key=lambda e: e["ts_ms"])
        res = run_stack(evs, CAPITAL, machine_fn, fh)
        out[nm] = res
        log(f"[machine] {nm}: {res['n']} trades, ${res['balance']:,.2f}, DD {res['max_dd']:.1f} %")
    all_ev = sorted(sum(flux.values(), []), key=lambda e: e["ts_ms"])
    out["STACK_MACHINE"] = run_stack(all_ev, CAPITAL, machine_fn, fh)
    log(f"[machine] STACK: ${out['STACK_MACHINE']['balance']:,.2f}, "
        f"DD {out['STACK_MACHINE']['max_dd']:.1f} %")
    return out


def daily_stream(res: dict) -> pd.Series:
    """PnL $ journalier (par heure de SORTIE), base $100."""
    d: dict = {}
    for t in res["trades"]:
        day = t["exit_ts"].date()
        d[day] = d.get(day, 0.0) + t["pnl"]
    return pd.Series(d).sort_index()


def corr_table(streams: dict[str, pd.Series], ref: pd.Series) -> list[str]:
    lines = ["| Flux | Pearson (jours) | Spearman | jours actifs communs | corr jours actifs |",
             "|---|---|---|---|---|"]
    for nm, s in streams.items():
        idx = ref.index.union(s.index)
        x = ref.reindex(idx, fill_value=0.0)
        y = s.reindex(idx, fill_value=0.0)
        if x.std() == 0 or y.std() == 0:
            lines.append(f"| {nm} | — | — | — | — |")
            continue
        pear = float(np.corrcoef(x, y)[0, 1])
        spear = float(x.rank().corr(y.rank()))
        both = (x != 0) & (y != 0)
        nb = int(both.sum())
        act = float(np.corrcoef(x[both], y[both])[0, 1]) if nb > 10 else np.nan
        lines.append(f"| {nm} | {pear:+.2f} | {spear:+.2f} | {nb} | {act:+.2f} |"
                     if np.isfinite(act) else f"| {nm} | {pear:+.2f} | {spear:+.2f} | {nb} | — |")
    return lines


# ------------------------------------------------------------------------ main
def main() -> int:
    now = datetime.now(timezone.utc)
    log("[reload] rejeu du moteur T21 (assert trade-par-trade)...")
    trades = load_carry_trades()
    val = np.array([t["ts"] >= VAL_START_MS for t in trades])
    mae_max = max(t["mae"] for t in trades)
    lev_cap = 100 / (mae_max + 0.5)

    # les trois conventions (sommes cumulées % notionnel)
    r_asis = np.array([t["gross"] - COST_RT * 100 + t["f_asis"] for t in trades])
    r_t21x = np.array([t["gross"] - COST_RT * 100 + t["f_exact"] for t in trades])
    r_har = np.array([t["gross_har"] - COST_RT * 100 + t["f_exact"] for t in trades])
    f_tot = sum(t["f_exact"] for t in trades)
    f_asis_tot = sum(t["f_asis"] for t in trades)
    g_t21 = sum(t["gross"] for t in trades)
    g_har = sum(t["gross_har"] for t in trades)
    fees_tot = COST_RT * 100 * len(trades)
    n_long = sum(1 for t in trades if t["dir"] == 1)
    log(f"[reload] {len(trades)} trades ({int((~val).sum())} TRAIN / {int(val.sum())} VAL) | "
        f"ASIS {r_asis.sum():+.1f}% · T21-ex {r_t21x.sum():+.1f}% · HARNAIS {r_har.sum():+.1f}%")

    L: list[str] = [
        "# T22 — TEST DU WALLET SÉQUENTIEL : le carry de funding (T21) à la porte",
        f"{now:%d/%m/%Y %H:%M} UTC · one-shot `scripts/studies/aster_carry_wallet.py` · "
        f"DB ro · harnais `scripts/stacked_portfolio.run_stack` (importé, non modifié) · "
        f"wallet $100 composé, marge fixe {MARGIN * 100:.0f} %, un slot (sérialisé), "
        f"frais 8 bps RT, exécution open t+1, stop 5×ATR prioritaire (moteur T21 bit-exact, "
        f"assert trade-par-trade : 999/999 reproduits).",
        "",
        "## 0. AUDIT T21 — TROIS ÉCARTS DÉCOUVERTS À LA PORTE (anti-boucle)",
        "",
        "**(a) Unité funding ×8** : les events du cache sont espacés de **8,00 h** "
        "(médiane, 3 symboles) ; le moteur T21 somme le taux ffillé sur CHAQUE barre "
        "horaire (`fund[entry_i:i+1].sum()/1e4`) → chaque event compté ~8×.",
        "**(b) Dénomination short** : T21 calcule le gross short en `(entry/exit − 1)` "
        "(dénominé SORTIE) ; le harnais (`stacked_portfolio`, `the_machine`) en "
        "`(entry − exit)/entry` (dénominé ENTRÉE = économie réelle). Sur les gros stops "
        "5×ATR en crash, l'écart explose : Σ(E/X + X/E − 2) > 0, biais systématique.",
        "**(c) Sous-ensemble sérialisé** : le slot unique du wallet saute les signaux "
        "groupés — crash = funding extrême sur les 3 majeures à la fois = exactement là "
        "où le carry gagne (voir §1 bis).",
        "",
        f"Décomposition des {len(trades)} trades ({n_long} longs / {len(trades) - n_long} shorts), "
        f"sommes cumulées en % du notionnel :",
        "",
        "| Convention | somme | dont prix | dont frais | dont funding | WR | pire trade |",
        "|---|---|---|---|---|---|---|",
        f"| ASIS (T21 publié : ×8 + short-sortie) | {r_asis.sum():+.1f} % | {g_t21:+.1f} % | "
        f"{-fees_tot:+.1f} % | {f_asis_tot:+.1f} % | {(r_asis > 0).mean() * 100:.1f} % | {r_asis.min():+.1f} % |",
        f"| T21-exact (funding exact, short-sortie) | {r_t21x.sum():+.1f} % | {g_t21:+.1f} % | "
        f"{-fees_tot:+.1f} % | {f_tot:+.1f} % | {(r_t21x > 0).mean() * 100:.1f} % | {r_t21x.min():+.1f} % |",
        f"| **HARNAIS (funding exact + short-entrée)** | **{r_har.sum():+.1f} %** | {g_har:+.1f} % | "
        f"{-fees_tot:+.1f} % | {f_tot:+.1f} % | {(r_har > 0).mean() * 100:.1f} % | {r_har.min():+.1f} % |",
        "",
        f"Split TRAIN/VAL en HARNAIS : TRAIN {int((~val).sum())} tr {r_har[~val].sum():+.1f} % "
        f"(wr {(r_har[~val] > 0).mean() * 100:.0f} %) · VAL {int(val.sum())} tr "
        f"{r_har[val].sum():+.1f} % (wr {(r_har[val] > 0).mean() * 100:.0f} %). "
        f"Côtés (HARNAIS) : TRAIN long "
        f"{sum(t['gross_har'] - COST_RT * 100 + t['f_exact'] for t, v in zip(trades, val) if t['dir'] == 1 and not v):+.0f} % / "
        f"short {sum(t['gross_har'] - COST_RT * 100 + t['f_exact'] for t, v in zip(trades, val) if t['dir'] == -1 and not v):+.0f} % ; "
        f"VAL long {sum(t['gross_har'] - COST_RT * 100 + t['f_exact'] for t, v in zip(trades, val) if t['dir'] == 1 and v):+.0f} % / "
        f"short {sum(t['gross_har'] - COST_RT * 100 + t['f_exact'] for t, v in zip(trades, val) if t['dir'] == -1 and v):+.0f} % "
        f"— les deux côtés INVERSENT leur signe entre TRAIN et VAL : aucun n'est stationnaire.",
        "",
        f"Risque : maxMAE {mae_max:.1f} % (prix, inchangé) → **lev cap 0-liq {lev_cap:.2f}×** ; "
        f"pire trade HARNAIS {r_har.min():+.1f} % ×2,1 = {r_har.min() * 2.1:+.1f} % de marge (survit à la règle).",
        "",
        "## 1. WALLET SÉQUENTIEL — BLOC STATS PAR LEVIER (HARNAIS, marge 10 %)",
        ""]

    wallets = {}
    for lev in LEVS:
        w = run_wallet(trades, "EXACT", lev, f"HARNAIS lev {lev:g}× (marge 10 %, 1 slot)")
        wallets[lev] = w
        L += w["lines"] + [""]

    L += ["### Mémoire : le même wallet sur la convention ASIS (T21 publié, ×8 — invalide)", ""]
    for lev in LEVS:
        w = run_wallet(trades, "ASIS", lev, f"ASIS lev {lev:g}×")
        L += w["lines"] + [""]

    w3 = run_wallet(trades, "EXACT", 2.1, "HARNAIS lev 2,1× — 3 slots (BTC/ETH/SOL indépendants)", slots=3)
    L += ["### Variante 3 slots (une position par majeure, marge 10 % chacune)", ""]
    L += w3["lines"] + [""]

    # --- §1 bis : diagnostic pris vs sautés (le mécanisme c) ---
    events, fh = to_events(trades, "EXACT", 2.1)
    res1 = run_stack(events, CAPITAL, lambda e: MARGIN, fh)
    taken_ks = sorted(int(t["sym"].split("#")[1]) for t in res1["trades"])
    mask_t = np.zeros(len(trades), bool)
    mask_t[taken_ks] = True
    sum_t, sum_s = r_har[mask_t].sum(), r_har[~mask_t].sum()
    sum_t21_t, sum_t21_s = r_t21x[mask_t].sum(), r_t21x[~mask_t].sum()
    L += ["### §1 bis — POURQUOI le wallet détruit l'edge : pris vs sautés (slot unique)",
          "",
          f"Le slot unique prend {mask_t.sum()}/{len(trades)} trades. Or les trades "
          f"SAUTÉS (signaux groupés : crash → funding extrême simultané sur les 3 "
          f"majeures) portent l'edge :",
          "",
          f"| Ensemble | somme HARNAIS | somme T21-exact |",
          f"|---|---|---|",
          f"| PRIS ({mask_t.sum()} trades, slots sériels) | {sum_t:+.1f} % | {sum_t21_t:+.1f} % |",
          f"| SAUTÉS ({int((~mask_t).sum())} trades) | {sum_s:+.1f} % | {sum_t21_s:+.1f} % |",
          f"| Total (3 slots, tous pris) | {r_har.sum():+.1f} % | {r_t21x.sum():+.1f} % |",
          "",
          f"Même à 3 slots (tous pris), le carry HARNAIS reste perdant une fois composé "
          f"(${w3['res']['balance']:,.2f}) : l'anti-compounding (pertes groupées aux "
          f"sommets d'équité pendant les crashes, gains aux creux) retourne une somme "
          f"arithmétique déjà négative en wallet encore pire.",
          ""]

    # --- splits temporels ---
    tr_tr = [t for t in trades if t["ts"] < VAL_START_MS]
    tr_va = [t for t in trades if t["ts"] >= VAL_START_MS]
    wtr = run_wallet(tr_tr, "EXACT", 2.1, "TRAIN 21-23 seul (HARNAIS 2,1×)")
    wva = run_wallet(tr_va, "EXACT", 2.1, "VAL 24-26 seul (HARNAIS 2,1×)")
    L += ["### Splits temporels (HARNAIS, 2,1×)", ""]
    L += wtr["lines"] + [""]
    L += wva["lines"] + [""]

    # --------------------------------------------------------- corrélations
    log("[corr] replay machine...")
    mach = replay_machine()
    carry_exact = daily_stream(wallets[2.1]["res"])
    streams_m = {nm: daily_stream(res) for nm, res in mach.items()}
    L += ["## 2. DÉCORRÉLATION AVEC LE STACK EXISTANT", "",
          "Flux machine rejoués seuls (sizing canonique K=0,89 copié de `the_machine.py`, "
          "leviers canoniques, rets journaliers base $100) vs carry HARNAIS 2,1×, "
          "fenêtre commune 2021→2026. CAVEAT : le replay couvre TOUTE l'histoire des "
          "klines (BNB/XRP/DOGE n'existent qu'à partir de 2025-09) — le cascade_majors 10× "
          "y subit des liqs antérieures à 2025 que le rapport officiel machine (fenêtre "
          "1 an, 0 liq, MAE gated 7,84 %) ne voit pas ; les corrélations restent valides "
          "comme mesure de co-mouvement journalier.", ""]
    L += corr_table(streams_m, carry_exact)
    stack_only = {"STACK_MACHINE": streams_m["STACK_MACHINE"]}
    L += ["", "Carry vs stack complet (les 4 flux empilés) — lecture : Pearson pleine "
              "fenêtre diluée par les jours à zéro ; la colonne « corr jours actifs » "
              "(les 2 flux actifs le même jour) est la plus informative :", ""]
    L += corr_table(stack_only, carry_exact)

    # ------------------------------------------------------------ verdict
    w21 = wallets[2.1]
    res21 = w21["res"]
    rois = [r["roi"] for r in w21["mr"]]
    st = streams_m["STACK_MACHINE"]
    idx = carry_exact.index.union(st.index)
    pear_stack = float(np.corrcoef(carry_exact.reindex(idx, fill_value=0),
                                   st.reindex(idx, fill_value=0))[0, 1])
    both = (carry_exact.reindex(idx, fill_value=0) != 0) & (st.reindex(idx, fill_value=0) != 0)
    x_a = carry_exact.reindex(idx, fill_value=0)[both]
    y_a = st.reindex(idx, fill_value=0)[both]
    act_stack = float(np.corrcoef(x_a, y_a)[0, 1]) if both.sum() > 10 else np.nan
    L += ["## 3. VERDICT PROMOTION", "",
          f"**REFUS — le carry T21 ne passe PAS la porte du wallet séquentiel, et pour "
          f"trois raisons empilées, chacune suffisante :**",
          "",
          f"1. **L'edge publié était un artefact d'unité** : +{r_asis.sum():.0f} % annoncés → "
          f"{r_t21x.sum():+.0f} % une fois le funding compté exactement (×8), puis "
          f"**{r_har.sum():+.0f} %** en économie harnais (short dénominé entrée) : le "
          f"« meilleur edge régime-indépendant » de T21 est un PnL NÉGATIF brut.",
          f"2. **La sérialisation dilue un edge déjà mort** : le slot unique prend "
          f"{int(mask_t.sum())}/{len(trades)} trades pour {sum_t21_t:+.0f} % (T21-exact) "
          f"et saute {int((~mask_t).sum())} trades à {sum_t21_s:+.0f} % — les clusters de "
          f"crash (funding extrême simultané) sont un peu plus riches mais, en économie "
          f"harnais, PRIS {sum_t:+.0f} % et SAUTÉS {sum_s:+.0f} % : aucun sous-ensemble "
          f"n'est gagnant.",
          f"3. **Même tous pris (3 slots)** : ${w3['res']['balance']:,.2f} — DD "
          f"{w3['res']['max_dd']:.1f} %, {sum(1 for x in w3['mr'] if x['roi'] < 0)} mois "
          f"négatifs — l'anti-compounding (pertes groupées aux sommets, gains aux creux) "
          f"achève un edge arithmétique déjà négatif.",
          "",
          f"Seule survie : la **frontière 0-liq tient** (0 liq aux 3 leviers, maxMAE "
          f"{mae_max:.1f} % < {100 / 2.1 - 0.5:.1f} % @2,1×, pire trade {r_har.min():+.1f} % "
          f"×2,1 = {r_har.min() * 2.1:+.1f} % de marge) et la corrélation au stack est "
          f"faible (Pearson {pear_stack:+.2f}, jours actifs {act_stack:+.2f}) — mais un "
          f"flux négatif décorrelé n'est pas de la diversification, c'est une fuite.",
          "",
          "**Conséquences registre** : `carry_thr-0.5+2.0_h48` rétrogradé SURVIVANT→NUL "
          "(artefact d'unité + dénomination short) ; `carry_thr-1.0+3.0_h72` et "
          "`carry_q10q90_h24` à re-auditer avec le même triple contrôle avant toute "
          "promotion ; le moteur d'étude T21 doit passer au convention harnais "
          "(funding event-based + short dénominé entrée) avant tout futur backtest carry.",
          ""]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    log(f"[write] {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
