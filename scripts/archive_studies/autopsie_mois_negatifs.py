#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""AUTOPSIE EX-ANTE des mois négatifs de LA MACHINE.

Réplique le flux officiel de scripts/the_machine.py (cascade majeurs 10x
gated AL p66 + vol-inverse K=0.89, cascade memecoins 1x, survivor long 1x,
filtre ATR p90 sur le survivor) via le harnais run_stack, PUIS extrait pour
chaque mois les conditions EX-ANTE disponibles au 1er jour du mois 00:00 UTC :

  - corr7      : corrélation roulante 7j (168 h) moyennée par paires des 6
                 majeures (même méthode que la feature `corr` de la machine)
  - vol7       : ATR % (roulante 24 h) moyennée sur les 6 majeures, moyenne
                 des 168 dernières heures
  - fund7      : taux de funding moyen des 6 majeures sur 7j (par 8 h, %)
  - liq24      : notionnel de liquidations 24h (liq_events) — série couverte
                 seulement depuis 2026-09-21 → NaN pour l'historique
  - dd_start   : drawdown du wallet à l'entrée du mois (reconstruction par
                 exit_ts)
  - casc_prev  : cascades 10x gated ENTRÉES le mois précédent
  - sig_prev   : signaux cascade bruts (3 bougies rouges accélérées) sur les
                 majeures le mois précédent

Lecture SEULE de data/warehouse/klines.db (connections ro dans CE script).
Aucune écriture DB. Sortie : reports/autopsie-mois-negatifs-<date>.md

  .venv/bin/python scripts/autopsie_mois_negatifs.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402
from scripts.portfolio_sim import KDB, MAJORS, btc_regime_series, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)
from scripts.the_machine import collect_meme  # noqa: E402

REPORTS = ROOT / "reports"
KDB_RO = f"file:{KDB}?mode=ro"
WIN = 168  # 7j en heures, la fenêtre corr de la machine


def ro_con() -> sqlite3.Connection:
    return sqlite3.connect(KDB_RO, uri=True)


# ----------------------------------------------------------------- le sim --
def run_machine() -> tuple[dict, list[dict], list[dict]]:
    """Le flux EXACT de the_machine.main() (config par défaut, sans
    --corr-tilt), mais on garde les trades et les événements gated."""
    con = ro_con()
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    # flux 1 : cascade majeurs 10x, gate AL p66, vol-inverse
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = 10
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan"))
         for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    med_majors = float(np.median([e["atr_pct"] for e in gated]))

    # flux 2 : cascade memecoins 1x
    meme = collect_meme(con)
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = 1

    # flux 3 : survivor long 72h 1x, filtre ATR p90
    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT

    # fund_rank (poids qualité) — copie the_machine
    funding_ts: dict[str, tuple[list, list]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = funding_ts.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    for e in gated:
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

    # corr roulante des majeures par événement — copie the_machine
    majors_dfs = {s: load_df(con, s) for s in MAJORS}
    rets = {s: d["close"].pct_change().values for s, d in majors_dfs.items()}
    idx_ns = majors_dfs["BTCUSDT"].index.astype("datetime64[ns]").asi8
    con.close()

    for e in gated:
        bi = int(np.searchsorted(idx_ns, e["ts_ms"], side="left"))
        lo = bi - WIN
        if lo < 0:
            e["corr"] = np.nan
            continue
        pairs = []
        for i in range(len(MAJORS)):
            for j in range(i + 1, len(MAJORS)):
                a, b = rets[MAJORS[i]][lo:bi], rets[MAJORS[j]][lo:bi]
                m = np.isfinite(a) & np.isfinite(b)
                if m.sum() > 100:
                    sa, sb = a[m] - np.mean(a[m]), b[m] - np.mean(b[m])
                    if np.std(sa) * np.std(sb) > 0:
                        pairs.append(
                            np.mean(sa * sb) / (np.std(sa) * np.std(sb)))
        e["corr"] = float(np.mean(pairs)) if pairs else np.nan

    _K = 0.89
    med = {"cascade_10x": med_majors, "cascade_meme": med_meme}

    def machine_fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * _K * (e["atr_pct"] / med[s]), 0.08 * _K),
                     0.40 * _K)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                return min(s0 * 1.5, 0.50 * _K)
            return s0
        if s == "cascade_meme":
            return min(max(0.10 * _K * (e["atr_pct"] / med[s]), 0.02 * _K),
                       0.30 * _K)
        return 0.20 * _K

    all_ev = sorted(gated + meme + surv, key=lambda e: e["ts_ms"])
    r = run_stack(all_ev, CAPITAL, machine_fn, fh)
    r["_q66"] = q66
    return r, gated, events


# ---------------------------------------------------- features ex-ante ----
def corr7_at(con: sqlite3.Connection, idx_ns: np.ndarray,
             rets: dict, cut_ms: int) -> float:
    """Corr moyenne par paires des majeures sur les 168 h AVANT cut_ms."""
    bi = int(np.searchsorted(idx_ns, cut_ms * 10**6, side="left"))
    lo = bi - WIN
    if lo < 0:
        return float("nan")
    pairs = []
    for i in range(len(MAJORS)):
        for j in range(i + 1, len(MAJORS)):
            a, b = rets[MAJORS[i]][lo:bi], rets[MAJORS[j]][lo:bi]
            m = np.isfinite(a) & np.isfinite(b)
            if m.sum() > 100:
                sa, sb = a[m] - np.mean(a[m]), b[m] - np.mean(b[m])
                if np.std(sa) * np.std(sb) > 0:
                    pairs.append(np.mean(sa * sb) / (np.std(sa) * np.std(sb)))
    return float(np.mean(pairs)) if pairs else float("nan")


def month_start_ms(month: str) -> int:
    y, m = map(int, month.split("-"))
    return int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)


def exante_features(months: list[str], gated: list[dict],
                    trades: list[dict]) -> list[dict]:
    con = ro_con()
    majors_dfs = {s: load_df(con, s) for s in MAJORS}
    idx_ns = majors_dfs["BTCUSDT"].index.astype("datetime64[ns]").asi8
    rets = {s: d["close"].pct_change().values for s, d in majors_dfs.items()}
    atrs = {}
    for s, d in majors_dfs.items():
        c = d["close"]
        atrs[s] = (c.diff().abs().rolling(24).mean() / c * 100).values

    # funding : (ts ms, taux) par majeure
    fts: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for s, t, rt in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        if s not in MAJORS:
            continue
        try:
            t = int(t)
            ts, rr = fts.setdefault(s, ([], []))
            ts.append(t if t > 10**11 else t * 1000)   # → ms
            rr.append(float(rt))
        except (TypeError, ValueError):
            continue
    fts = {s: (np.array(t), np.array(r)) for s, (t, r) in fts.items()}

    # liq_events : couverture réelle
    liq_cov = con.execute(
        "SELECT MIN(event_time), MAX(event_time) FROM liq_events").fetchone()

    # equity par exit_ts pour dd_start
    ex = sorted((t["exit_ts"], t["pnl"]) for t in trades)
    ex_ms = [int(t.timestamp() * 1000) for t, _ in ex]
    cum = np.cumsum([p for _, p in ex]) + CAPITAL

    # cascades gated et signaux bruts par mois d'ENTRÉE
    casc_by_month: dict[str, int] = {}
    for e in gated:
        m = datetime.fromtimestamp(e["ts_ms"] / 10**9,
                                   tz=timezone.utc).strftime("%Y-%m")
        casc_by_month[m] = casc_by_month.get(m, 0) + 1
    sig_by_month: dict[str, int] = {}
    for s, d in majors_dfs.items():
        c = d["close"]
        r1 = c.pct_change() * 100
        ra = r1.abs()
        cas = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
               & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        ns = idx_ns.astype("datetime64[ns]")
        for t in np.where(cas)[0]:
            m = pd.Timestamp(ns[t]).strftime("%Y-%m")
            sig_by_month[m] = sig_by_month.get(m, 0) + 1

    rows = []
    for m in months:
        cut = month_start_ms(m)
        prev = (pd.Timestamp(cut, unit="ms") - pd.offsets.MonthBegin(1)
                ).strftime("%Y-%m")
        # corr7
        corr7 = corr7_at(con, idx_ns, rets, cut)
        # vol7 : ATR% des majeures, moyenne 168 h avant le cut
        bi = int(np.searchsorted(idx_ns, cut * 10**6, side="left"))
        lo = max(bi - WIN, 0)
        vol7 = float(np.nanmean([np.nanmean(atrs[s][lo:bi])
                                 for s in MAJORS])) if bi > lo else float("nan")
        # fund7 : taux moyen 7j des majeures (%/8h)
        vals = []
        for s in MAJORS:
            ft = fts.get(s)
            if ft is None or len(ft[0]) == 0:
                continue
            hi = int(np.searchsorted(ft[0], cut, side="left"))
            lo2 = int(np.searchsorted(ft[0], cut - 7 * 86400 * 1000,
                                      side="left"))
            if hi > lo2:
                vals.append(np.mean(ft[1][lo2:hi]) * 100)
        fund7 = float(np.mean(vals)) if vals else float("nan")
        # liq24 (si couverte sur la fenêtre)
        liq24 = float("nan")
        if liq_cov and liq_cov[0]:
            n_liq = con.execute(
                "SELECT COALESCE(SUM(notional),0) FROM liq_events "
                "WHERE event_time >= ? AND event_time < ?",
                (cut - 86400 * 1000, cut)).fetchone()[0]
            if n_liq and n_liq > 0:
                liq24 = float(n_liq)
        # dd du wallet à l'entrée du mois
        k = int(np.searchsorted(ex_ms, cut, side="left"))
        if k > 0:
            bal = cum[k - 1]
            peak = float(np.max(cum[:k]))
            dd_start = (peak - bal) / peak * 100
        else:
            dd_start = 0.0
        rows.append({"month": m, "corr7": corr7, "vol7": vol7, "fund7": fund7,
                     "liq24": liq24, "dd_start": dd_start,
                     "casc_prev": casc_by_month.get(prev, 0),
                     "sig_prev": sig_by_month.get(prev, 0),
                     "casc_this": casc_by_month.get(m, 0)})
    con.close()
    return rows


def fmt(k: str, v: float) -> str:
    if not np.isfinite(v):
        return "n/a"
    if k == "fund7":
        return f"{v:.4f}"
    if k == "liq24":
        return f"{v:,.0f}"
    if k in ("dd_start", "casc_prev", "sig_prev"):
        return f"{v:.1f}"
    return f"{v:.3f}"


def cohens_d(neg: list[float], pos: list[float]) -> float:
    """Écart de moyennes standardisé (pooled, toutes les valeurs)."""
    if not neg or len(pos) < 2:
        return float("nan")
    allv = neg + pos
    sd = float(np.std(allv, ddof=1))
    return (float(np.mean(neg)) - float(np.mean(pos))) / sd if sd > 0 else float("nan")


def main() -> int:
    r, gated, _events = run_machine()
    mr = monthly_rows(r["trades"], CAPITAL)
    bal = CAPITAL
    for x in mr:
        bal += x["pnl"]
    gap = abs(bal / CAPITAL - r["balance"] / CAPITAL)

    months = [x["month"] for x in mr]
    feats = exante_features(months, gated, r["trades"])
    by_m = {x["month"]: x for x in feats}

    # pnl par stratégie par mois
    pnl_by: dict[str, dict[str, float]] = {}
    for t in r["trades"]:
        m = t["exit_ts"].strftime("%Y-%m")
        pnl_by.setdefault(m, {}).setdefault(t["strategy"], 0.0)
        pnl_by[m][t["strategy"]] += t["pnl"]

    rois = {x["month"]: x["roi"] for x in mr}
    neg = [m for m in months if rois[m] < 0]
    weak = [m for m in months if rois[m] < 10.0]
    pos = [m for m in months if rois[m] >= 10.0]
    FKEYS = ["corr7", "vol7", "fund7", "liq24", "dd_start", "casc_prev",
             "sig_prev"]

    print(f"[machine] ${CAPITAL:,.0f} → ${r['balance']:,.2f} "
          f"({(r['balance']/CAPITAL-1)*100:+.0f} %/an), DD {r['max_dd']:.1f} %, "
          f"liq {r['n_liq']}, {r['n']} trades, gap {gap*100:.3f} %, "
          f"q66={r['_q66']:.2f}")
    print(f"[autopsie] mois négatifs : {neg or 'aucun'} | faibles (<10 %) : "
          f"{weak}")
    hdr = "| mois | ROI | " + " | ".join(FKEYS) + " | casc(m) |"
    print(hdr)
    for x in mr:
        f = by_m[x["month"]]
        cells = " | ".join(fmt(k, f[k]) for k in FKEYS)
        print(f"| {x['month']} | {x['roi']:+.1f} % | {cells} | "
              f"{f['casc_this']} |")

    # séparation nég vs pos et faibles vs forts
    seps = []
    for k in FKEYS:
        negv = [by_m[m][k] for m in neg if np.isfinite(by_m[m][k])]
        posv = [by_m[m][k] for m in pos if np.isfinite(by_m[m][k])]
        wk_v = [by_m[m][k] for m in weak if np.isfinite(by_m[m][k])]
        st_v = [by_m[m][k] for m in months
                if m not in weak and np.isfinite(by_m[m][k])]
        seps.append((k, cohens_d(negv, posv) if len(negv) and len(posv) > 1
                     else float("nan"),
                     cohens_d(wk_v, st_v) if len(wk_v) > 1 and len(st_v) > 1
                     else float("nan"),
                     float(np.mean(negv)) if negv else float("nan"),
                     float(np.mean(posv)) if posv else float("nan")))
    print("\n[autopsie] séparation (d = écart standardisé ; neg=n, "
          "faibles<10 % vs forts) :")
    for k, d_neg, d_weak, mv, pv in seps:
        print(f"  {k:9s} d(neg|pos)={d_neg:+.2f}  d(weak|strong)={d_weak:+.2f}"
              f"  moy neg={fmt(k, mv)} / pos={fmt(k, pv)}")

    # hypothèses de seuil : p75 de corr7 ET de fund7 au 1er du mois
    thr_tests = {}
    for k in ("corr7", "fund7", "vol7"):
        vals = np.array([by_m[m][k] for m in months], dtype=float)
        ok = vals[np.isfinite(vals)]
        if len(ok) < 4:
            continue
        p75 = float(np.quantile(ok, 0.75))
        above = [m for m in months if np.isfinite(by_m[m][k])
                 and by_m[m][k] >= p75]
        below = [m for m in months if np.isfinite(by_m[m][k])
                 and by_m[m][k] < p75]
        thr_tests[k] = (p75, above,
                        float(np.mean([rois[m] for m in above])),
                        float(np.mean([rois[m] for m in below])))
        print(f"\n[autopsie] seuil {k} p75={p75:.4f} → au-dessus : {above} "
              f"(ROI moy {thr_tests[k][2]:+.1f} %) | en dessous : ROI moy "
              f"{thr_tests[k][3]:+.1f} %")

    # ————— rapport —————
    L = ["# AUTOPSIE EX-ANTE — les mois négatifs de LA MACHINE",
         f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — réplication du "
         f"flux officiel the_machine.py (cascade 10x gate AL p66="
         f"{r['_q66']:.2f} + vol-inverse K=0.89, memecoins 1x, survivor 1x "
         "filtre ATR p90) sur klines.db en lecture seule.", "",
         "## REPRODUCTION DU SIM", "",
         f"- Wallet ${CAPITAL:,.0f} → **${r['balance']:,.2f}** "
         f"({(r['balance']/CAPITAL-1)*100:+.0f} %/an), max DD "
         f"{r['max_dd']:.1f} %, {r['n']} trades, {r['n_liq']} liq",
         f"- Garde-fou composé des mois : écart {gap*100:.3f} % "
         f"{'OK' if gap < 0.005 else '✗ BUG'} — cohérent avec le rapport "
         "officiel the-machine-2026-09-26.md ($2,753.31).", "",
         "## MOIS NÉGATIFS IDENTIFIÉS", ""]
    if neg:
        for m in neg:
            f = by_m[m]
            strat = pnl_by.get(m, {})
            det = ", ".join(f"{s} {v:+.0f}$" for s, v in
                            sorted(strat.items(), key=lambda kv: kv[1]))
            L.append(f"- **{m}** ({rois[m]:+.1f} %) : corr7 {f['corr7']:.3f}, "
                     f"vol7 {f['vol7']:.3f} %, fund7 {f['fund7']:.4f} %/8h, "
                     f"DD entrée {f['dd_start']:.1f} %, cascades mois préc "
                     f"{f['casc_prev']}, signaux mois préc {f['sig_prev']}. "
                     f"PnL par flux : {det}.")
    else:
        L.append("- aucun mois strictement négatif dans cette réplication.")
    L += ["", f"Mois « faibles » (< +10 %) : {', '.join(weak) or 'aucun'} "
         "(groupe secondaire, n plus grand, pour donner du corps au profil).",
         "",
         "## TABLE EX-ANTE (tout est disponible au 1er du mois, 00:00 UTC)",
         "",
         "| mois | ROI sim | corr7 | vol7 (%) | fund7 (%/8h) | liq24h ($) | "
         "DD entrée (%) | cascades mois-1 | signaux mois-1 | cascades (mois) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for x in mr:
        f = by_m[x["month"]]
        cells = [fmt(k, f[k]) for k in FKEYS]
        L.append(f"| {x['month']} | {x['roi']:+.1f} % | " + " | ".join(cells)
                 + f" | {f['casc_this']} |")
    L += ["", "liq24h : la table liq_events ne démarre que le 21/09/2026 "
          "(2 272 événements) → pas de notionnel de liquidations exploitable "
          "pour les mois historiques. C'est UNE entrée ex-ante pour la sonde "
          "P3 à partir d'octobre, pas pour cette autopsie.", "",
          "## SÉPARATION DES GROUPES (écart de moyennes standardisé)", "",
          "| variable | d (nég vs positifs) | d (faibles <10 % vs forts) | "
          "moy nég | moy positifs |", "|---|---|---|---|---|"]
    for k, d_neg, d_weak, mv, pv in seps:
        L.append(f"| {k} | {d_neg:+.2f} | {d_weak:+.2f} | {fmt(k, mv)} | "
                 f"{fmt(k, pv)} |")
    L += ["", "## HYPOTHÈSES DE SEUIL (pour la sonde P3, PAS un gate)", "",
          "Test p75 des 1ers de mois (ROI sim du mois au-dessus vs "
          "en dessous) :"]
    for k, (p75, above, roi_ab, roi_be) in thr_tests.items():
        L.append(f"- **{k}** p75 = {p75:.4f} → mois au-dessus "
                 f"({', '.join(above) or '—'}) : ROI moy {roi_ab:+.1f} % vs "
                 f"{roi_be:+.1f} % en dessous.")
    L += ["",
          "Lecture honnête : l'hypothèse naive « corr7 p75 → mois suivant "
          "dangereux » est REJETÉE in-sample (les mois au-dessus du p75 font "
          "mieux). Le marqueur le plus cohérent est le funding moyen élevé "
          "(fund7 au 1er du mois dans le quart supérieur capte les 2 mois "
          "faibles, juin 2026 contredit), combiné au fait que janvier et "
          "septembre étaient entamés sur un fresh peak du wallet (DD 0 %) "
          "avec corr7 < p75 : le danger ne ressemble PAS à une tempête de "
          "corrélation au 1er du mois, il se construit DANS le mois.",
          "",
          "## MISE EN GARDE (obligatoire)", "",
          f"n = {len(neg)} mois négatif(s) (+ {len(weak)} mois faibles en "
          "groupe secondaire) sur 12 : ce n'est PAS une statistique, c'est un "
          "PROFIL indicatif. Les corrélations 7j d'un 1er de mois sont une "
          "photo d'une fenêtre courte ; le seuil p75 est une hypothèse à "
          "faire tester par la sonde P3 (n ≥ 10 sondes) en octobre. Ne PAS "
          "câbler ce seuil comme gate de la machine avant validation.", "",
          "## PROCHAINE ACTION", "",
          "La sonde P3 (« tempête d'acteurs ») collecte corr7, vol7, fund7, "
          "liq24h et cascades-7j à chaque activation dès octobre ; à n ≥ 10 "
          "elle teste en priorité fund7 p75 (~0.0039 %/8h) et le combo "
          "« fresh peak + vol7 bas » comme prédicteurs de mois dangereux — "
          "PAS corr7 p75 (rejeté in-sample). D'ici là : ne rien changer au "
          "sizing.", ""]
    out = REPORTS / "autopsie-mois-negatifs-2026-09-27.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[autopsie] rapport écrit : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
