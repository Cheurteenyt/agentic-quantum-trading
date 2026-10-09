#!/usr/bin/env python
"""LE PORTEFEUILLE EMPILÉ — plusieurs stratégies, un seul wallet.

La leçon du projet : la stabilité vient de l'EMPILAGE d'edges
décorrelés, pas d'un seul signal. Ce simulateur fait tourner TROIS
stratégies validées au-dessus du drift dans le MÊME wallet :

  1. cascade 20x (majeures, hold 24h, maker) — gated par l'AL Score
  2. funding_divergence +12h (univers complet, 3x, taker) — la foule
     empile des longs pendant que le prix chute ≥ 3 %/24h
  3. confluence funding+vwap +24h (univers complet, 3x, taker) — la
     foule empile des longs et le prix est étiré ≥ 3σ au-dessus du vwap

Règles du wallet :
  - chaque stratégie a son propre créneau (pas deux positions de la
    même stratégie en même temps) ; les stratégies DIFFÉRENTES peuvent
    coexister — c'est le but
  - marge = % de la balance courante (compounding), par stratégie
  - liquidation en chemin : MAE ≥ 100/lev − maintMarginPercent du symbole
    (liq_move_for ; le « − 0,5 % » hérité du pré-F-038 ne valait que pour
    les majeures à maint 0,5 % — obsolète depuis F-038, corrigé R3/B-B)
  - funding réel pendant détention (le short reçoit le taux positif)

Comparaisons : chaque stratégie SEULE (exposition moyenne 5 %) vs
EMPILÉE (cascade ~3 %, fdiv 1,5 %, confluence 1 %) vs EMPILÉE ×2 vs
ORACLE (les trades voués à la liquidation ne sont pas pris).

  .venv/bin/python scripts/stacked_portfolio.py
"""
from __future__ import annotations

import heapq
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.funding_series import FundingSeries, funding_series_all  # noqa: E402,F401
from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAJORS, btc_regime_series, lev_capped, liq_move_for, monthly_rows)

REPORTS = ROOT / "reports"
CAPITAL = 100.0
TAKER_RT = (4 + 10) * 2      # bps aller-retour sur le notionnel
MAKER_RT = (2 + 0) * 2


def funding_hourly_all() -> dict[str, "FundingSeries"]:
    """FIX lot2 (F3+F12) : retourne les SÉRIES de funding réelles par symbole.

    L'intégration as-of (sum_pct_between) remplace la moyenne full-sample —
    un trade 2022 ne reçoit plus la moyenne 2022-2026 — et l'intervalle est
    MESURÉ (médiane des gaps), jamais supposé 8h. Le nom historique est
    conservé : 20+ appelants passent le dict à run_stack sans l'ouvrir.
    """
    return funding_series_all()


def collect_funding_strategies(con: sqlite3.Connection
                               ) -> tuple[list[dict], list[dict]]:
    """funding_divergence +12h et confluence funding+vwap +24h.

    Signal commun : le funding accélère (taux ≥ p90 de ses 30 derniers
    jours, positif = la foule empile des longs).
      - fdiv : ET le prix a chuté ≥ 3 %/24h (short la continuation)
      - conf : ET le prix est ≥ 3σ au-dessus du vwap 7j (short l'épuisement)
    """
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol")]
    fdiv: list[dict] = []
    conf: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 800:
            continue
        rows = con.execute(
            "SELECT funding_time, rate FROM funding_history "
            "WHERE symbol = ? ORDER BY funding_time", (sym,)).fetchall()
        if len(rows) < 50:
            continue
        ts = np.array([int(t) * 10**6 if int(t) > 10**11 else int(t) * 10**9
                       for t, _ in rows])
        rates = np.array([float(r) for _, r in rows])
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        # le taux as-of, en pas d'heure (dernier taux connu ≤ t)
        pos = np.searchsorted(ts, idx_ns, side="right") - 1
        rate_h = np.where(pos >= 0, rates[np.clip(pos, 0, None)], np.nan)
        rate_s = pd.Series(rate_h, index=idx)
        p90 = rate_s.rolling(720, min_periods=100).quantile(0.9)
        accel = (rate_s >= p90) & (rate_s > 0)

        close = df["close"]
        volume = df["volume"]
        highs = df["high"].values
        opens = df["open"].values
        ret24 = close.pct_change(24) * 100
        vwap168 = ((close * volume).rolling(168).sum()
                   / volume.rolling(168).sum().replace(0, float("nan")))
        vwap_dev = (close - vwap168) / vwap168 * 100
        mu = vwap_dev.rolling(720, min_periods=100).mean()
        sd = vwap_dev.rolling(720, min_periods=100).std()
        conf_sig = (accel & (vwap_dev >= mu + 3 * sd)).fillna(False)
        fdiv_sig = (accel & (ret24 <= -3)).fillna(False)

        for name, sig, lev, hold in (("funding_div", fdiv_sig, 3, 12),
                                     ("confluence", conf_sig, 3, 24)):
            fee_rt = TAKER_RT
            # FIX F-038 — le levier really exécutable : 75 symboles de
            # l'univers ont max_leverage < 3 (8 sans valeur), Aster refuse
            # l'ordre au-delà. On plafonne, on ne rejette pas : le trade reste
            # dans le portefeuille mais au levier que l'exchange accepte.
            lev_eff = lev_capped(sym, lev)
            if lev_eff <= 0:
                continue
            for t in np.where(sig)[0]:
                ei = t + 1
                if ei + hold >= len(idx_ns) or t < 300:
                    continue
                entry = opens[ei]
                if entry <= 0 or not np.isfinite(rate_h[t]):
                    continue
                exit_j = ei + hold - 1
                if exit_j >= len(idx_ns):
                    continue
                exit_px = df["close"].values[exit_j]
                out = {"sym": sym, "ts_ms": int(idx_ns[ei]),
                       "strategy": name, "lev": lev_eff, "hold_h": hold,
                       "fee_rt_bps": fee_rt,
                       "entry": entry, "exit": exit_px,
                       "price_ret_short": (entry - exit_px) / entry * 100,
                       "mae_adverse": (highs[ei:exit_j + 1].max() - entry)
                       / entry * 100}
                (fdiv if name == "funding_div" else conf).append(out)
    return fdiv, conf


def _size_fn_arity(fn) -> int:
    """Le nombre de params acceptés par un sizing fn (2 = avec état)."""
    import inspect
    try:
        return len(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return 1


def run_stack(events: list[dict], capital: float, size_fn,
              funding_hourly: dict[str, float], oracle: bool = False) -> dict:
    """Le wallet multi-stratégies. size_fn(e) -> taille marge (0-1).

    FIX lot3 (F8) : le PnL d'un trade sain est booké À SA SORTIE (l'ancien
    bookage à l'entrée figeait le futur dans le chemin d'équité), et les
    marks horaires de l'event (e["marks"] = [(dt_h, ret_pct côté position)])
    dessinent le chemin latent : max_dd voit désormais le drawdown
    intratrade. Sans marks sur l'event, le DD = le chemin des sorties
    réalisées. Le sizing reste sur le réalisé (convention inchangée).
    """
    if size_fn is None:
        # FIX lot1 (F13) : le fallback None faisait `sz = size` — un
        # NameError latent au milieu de la boucle. On refuse tôt.
        raise ValueError("size_fn requis : passe un sizer (e) -> taille marge 0-1")
    balance = capital                    # le cash RÉALISÉ
    peak = trough = balance              # chemin réalisé (sorties + sizing)
    peak_lat = trough_lat = balance      # chemin latent (marks intratrade)
    max_dd = 0.0
    busy: dict[str, int] = {}
    trades: list[dict] = []
    n = n_liq = n_wins = 0
    fees_tot = fund_tot = 0.0
    exits_due: list[tuple[int, int, float, dict]] = []
    marks_due: list[tuple[int, int, float, float]] = []
    _seq = 0

    def _drain(limit_ns: int) -> None:
        """Bookage chronologique strict : à timestamp égal, la sortie
        (réalisation) précède le mark (latent)."""
        nonlocal balance, peak, trough, peak_lat, trough_lat, max_dd
        while exits_due or marks_due:
            t_e = exits_due[0][0] if exits_due else limit_ns + 1
            t_m = marks_due[0][0] if marks_due else limit_ns + 1
            if min(t_e, t_m) > limit_ns:
                break
            if t_e <= t_m:
                _, _, pnl, tr = heapq.heappop(exits_due)
                balance += pnl
                tr["balance"] = balance
                trades.append(tr)
                peak = max(peak, balance)
                dd = (peak - balance) / peak * 100 if peak > 0 else 0.0
                max_dd = max(max_dd, dd)
                trough = min(trough, balance)
            else:
                _, _, m_notional, m_ret = heapq.heappop(marks_due)
                eq = balance + m_notional * m_ret / 100.0
                peak_lat = max(peak_lat, eq)
                dd = (peak_lat - eq) / peak_lat * 100 if peak_lat > 0 else 0.0
                max_dd = max(max_dd, dd)
                trough_lat = min(trough_lat, eq)

    for e in events:                       # events triés par ts
        if balance <= 1:
            break
        _drain(e["ts_ms"])                 # sorties et latent dus AVANT cet event
        if busy.get(e["strategy"], 0) > e["ts_ms"]:
            continue                       # la stratégie est déjà en position
        # FIX F-038 — maintMarginPercent réel par symbole (le -0.5 dur
        # repoussait la ligne de mort de 4,5 % au lieu de 2,5 % sur les
        # majeures, et de 16,16 % au lieu de 16,66 % sur les 365 symboles
        # à maint 16,66 % : sous-comptage des liquidations partout).
        liq_move = liq_move_for(e["sym"], e["lev"])
        if oracle and e["mae_adverse"] >= liq_move:
            continue                       # l'oracle ne le prend pas
        # le sizing peut recevoir l'état du wallet (balance, drawdown courant) :
        # dispatch par introspection — un except TypeError masquerait les
        # vraies erreurs internes du sizing
        dd_now = (peak - balance) / peak * 100 if peak > 0 else 0.0
        if _size_fn_arity(size_fn) >= 2:
            sz = size_fn(e, {"balance": balance, "dd": dd_now, "peak": peak})
        else:
            sz = size_fn(e)
        if sz <= 0:
            continue
        margin = balance * sz
        notional = margin * e["lev"]
        fees = notional * e["fee_rt_bps"] / 10000
        # FIX lot2 (F3) : le funding réellement applicable sur (entrée, sortie]
        # — la moyenne full-sample fabriquait un look-ahead (un trade 2022
        # recevait la moyenne 2022-2026). Shim float : appelants RO legacy.
        fser = funding_hourly.get(e["sym"])
        if fser is None:
            fund = 0.0
        elif hasattr(fser, "sum_pct_between"):
            _t0 = e["ts_ms"] / 1e6
            fund = notional * fser.sum_pct_between(
                _t0, _t0 + e["hold_h"] * 3_600_000.0) / 100.0
        else:
            fund = notional * fser / 100.0 * e["hold_h"]
        # fund_sign : +1 = short (reçoit le funding positif), -1 = long (le paie)
        pnl = (e["price_ret_short"] / 100 * notional
               + e.get("fund_sign", 1) * fund - fees)
        liq = e["mae_adverse"] >= liq_move or pnl <= -margin
        if liq:
            pnl = -margin
            n_liq += 1
        fees_tot += fees
        fund_tot += fund
        n += 1
        n_wins += pnl > 0
        exit_ns = e["ts_ms"] + e["hold_h"] * 3600 * 10**9  # ts_ms = NS
        liq_ts_dt = None
        if liq and e.get("liq_ts_ms"):
            liq_ts_dt = datetime.fromtimestamp(e["liq_ts_ms"] / 10**9,
                                               tz=timezone.utc)
        # PR-169 (P1 composition) : le créneau se libère à la FIN RÉELLE
        # de la position — une liq morte à h5 libère le flux à h5, pas à
        # la sortie prévue h24 (135/901 créneaux fdiv bloqués à tort dans
        # le rapport du 03/10). Même sémantique que run_wallet_mtm
        # (liq_ts_ms porte des NS malgré son nom — /10**9 ci-dessus).
        busy[e["strategy"]] = (e["liq_ts_ms"]
                               if liq and e.get("liq_ts_ms") else exit_ns)
        tr = {"sym": e["sym"], "strategy": e["strategy"],
              "entry_ts": datetime.fromtimestamp(
                  e["ts_ms"] / 10**9, tz=timezone.utc),
              # PR-169 (P2) : le bucketing mensuel utilise la fin RÉELLE —
              # l'ancien exit_ts prévu plaçait la perte de liq au mois de
              # sortie prévue (mtm la place au mois de mort réel)
              "exit_ts": (liq_ts_dt if liq and liq_ts_dt else
                          datetime.fromtimestamp(exit_ns / 10**9,
                                                 tz=timezone.utc)),
              "pnl": pnl, "balance": balance, "liq": liq,
              "entry": e.get("entry"), "margin": margin,
              "liq_price": e.get("liq_price") if liq else None,
              "liq_ts": liq_ts_dt,
              # Fossile ronde 5 : le registre n'avait pas le levier du trade
              # — son fallback « prix de mort » utilisait 100/3−0.5 en dur
              "lev": e.get("lev")}
        if liq:
            # le sort est scellé à l'entrée (MAE connu) : booké immédiatement
            balance += pnl
            tr["balance"] = balance
            trades.append(tr)
            peak = max(peak, balance)
            dd = (peak - balance) / peak * 100 if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
            trough = min(trough, balance)
        else:
            heapq.heappush(exits_due, (exit_ns, _seq, pnl, tr))
            for dt_h, ret_pct in e.get("marks", ()):
                heapq.heappush(marks_due, (
                    e["ts_ms"] + int(float(dt_h) * 3600 * 10**9),
                    _seq, notional, float(ret_pct)))
            _seq += 1
    _drain(10**30)                         # la fin : tout ce qui reste est dû
    return {"balance": balance, "max_dd": max_dd, "trough": trough,
            "trades": trades, "n": n, "n_liq": n_liq, "n_wins": n_wins,
            "fees": fees_tot, "funding": fund_tot}


def stamp_expanding_q66(events: list[dict], min_hist: int = 30,
                        q: float = 2 / 3) -> tuple[list[dict], float]:
    """C-B3 — colle `_q66_asof` sur chaque event.

    AVANT (le bug) :

        k = int(len(cascade) * 0.7)
        q66 = np.nanquantile([e["al_score"] for e in cascade[:k]], 2/3)

    Un SEUL quantile, calculé sur les 70 % premiers du sample (car
    `collect_featured` trie par `ts_ms`, anti_liq.py:83), puis appliqué à
    TOUS les événements — y compris les 30 % finaux. Le seuil de sizing au
    temps t voyait donc jusqu'à 70 % d'histoire future : look-ahead plein.

    Ici le seuil au temps t ne voit que les scores ANTERIEURS à t, sur un
    quantile EXPANDING — le même contrat que `the_machine.gate_expanding`
    (PR-167), qui a déjà été corrigé pour ce motif.

    Pendant le warm-up (`len(hist) < min_hist`) le seuil est NaN et
    l'event n'est PAS gaté : c'est la sémantique de `gate_expanding`
    (`elif np.isfinite(s): gated.append(e)`), pas une invention ici.

    Renvoie (events triés, dernier q66 as-of) pour le rapport.
    """
    ordre = sorted(events, key=lambda x: x["ts_ms"])
    hist: list[float] = []
    last = float("nan")
    for e in ordre:
        sc = e.get("al_score", float("nan"))
        if len(hist) >= min_hist:
            last = float(np.nanquantile(hist, q))
            e["_q66_asof"] = last
        else:
            e["_q66_asof"] = float("nan")
        if np.isfinite(sc):
            hist.append(sc)
    return ordre, last


def size_by_policy(policy: dict[str, float], gate_thr: float):
    """cascade : cool si score calme, 0 si chaud (gate) ; autres : plat.
    Score NaN (fenêtre pas assez remplie) = flat 0.05, la baseline.

    C-B3 : le seuil lu `_q66_asof` (quantile EXPANDING posé par
    `stamp_expanding_q66`), pas le scalaire `gate_thr`. Le scalaire reste
    le REPLI pour un event sans estampille — c'est lui qui évite que les
    trois appels `size_by_policy(..., q66)` cessent de fonctionner, et les
    stratégies funding_div/confluence ne l'utilisent de toute façon pas.
    """
    def fn(e: dict) -> float:
        s = e.get("strategy")
        if s == "cascade":
            sc = e.get("al_score", float("nan"))
            if np.isnan(sc):
                return 0.05
            thr = e.get("_q66_asof", gate_thr)
            if np.isnan(thr):
                return policy["cascade"]      # warm-up : pas de gate
            if sc >= thr:
                return 0.0
            return policy["cascade"]
        return policy.get(s, 0.0)
    return fn


def bloc(res: dict, label: str, capital: float) -> list[str]:
    n = max(res["n"], 1)
    pnls = [t["pnl"] for t in res["trades"]]
    return [
        f"**{label}** : {capital:,.0f} $ → **${res['balance']:,.2f}** "
        f"(ROI {(res['balance']/capital-1)*100:+.1f} %, DD {res['max_dd']:.1f} %)",
        f"  {res['n']} trades, WR {res['n_wins']/n*100:.1f} %, "
        f"liq {res['n_liq']} ({res['n_liq']/n*100:.1f} %), "
        f"frais ${res['fees']:,.2f}, funding ${res['funding']:+,.2f}, "
        f"espérance ${sum(pnls)/len(pnls):+.3f}" if pnls else "  aucun trade",
    ]


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    regime = btc_regime_series()
    fh = funding_hourly_all()

    # --- cascade 20x + AL Score (majeures) ---
    cascade = collect_featured(regime, "majors")
    for e in cascade:
        e["strategy"] = "cascade"
        e["lev"] = 20
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(cascade)
    # C-B3 : seuil AS-OF par événement (quantile expanding sur les seuls
    # scores antérieurs). L'ancien `q66` était un scalaire calculé sur les
    # 70 % premiers du sample puis appliqué aux 30 % finaux — look-ahead.
    # `q66` reste le DERNIER seuil as-of, pour le rapport seulement.
    cascade, q66 = stamp_expanding_q66(cascade)

    # --- funding_div + confluence (univers complet) ---
    fdiv, conf = collect_funding_strategies(con)
    con.close()

    all_ev = sorted(cascade + fdiv + conf, key=lambda e: e["ts_ms"])
    counts = defaultdict(int)
    for e in all_ev:
        counts[e["strategy"]] += 1

    lines = [
        "# LE PORTEFEUILLE EMPILÉ — 3 stratégies, un wallet",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"cascade {counts['cascade']} (AL gate ≥ p66={q66:.2f}), "
        f"funding_div {counts['funding_div']}, confluence {counts['confluence']}.",
        "", "## CHAQUE STRATÉGIE SEULE (exposition moyenne 5 %)", ""]
    alone = {}
    alone["cascade"] = run_stack(cascade, CAPITAL,
                                 size_by_policy({"cascade": 0.075}, q66), fh)
    alone["funding_div"] = run_stack(fdiv, CAPITAL,
                                     size_by_policy({"funding_div": 0.05}, q66), fh)
    alone["confluence"] = run_stack(conf, CAPITAL,
                                    size_by_policy({"confluence": 0.05}, q66), fh)
    for s in ("cascade", "funding_div", "confluence"):
        lines += bloc(alone[s], s, CAPITAL)

    # --- EMPILÉ ---
    stack_policy = size_by_policy({"cascade": 0.045, "funding_div": 0.015,
                                   "confluence": 0.01}, q66)
    stack = run_stack(all_ev, CAPITAL, stack_policy, fh)
    stack2 = run_stack(all_ev, CAPITAL, stack_policy, fh) if False else None
    # ×2 : tailles doublées
    def policy2(e: dict) -> float:
        return stack_policy(e) * 2
    stack2 = run_stack(all_ev, CAPITAL, policy2, fh)
    oracle = run_stack(all_ev, CAPITAL, policy2, fh, oracle=True)

    lines += ["", "## EMPILÉ (cascade ~3 % / fdiv 1,5 % / confluence 1 %)", ""]
    lines += bloc(stack, "EMPILÉ ×1", CAPITAL)
    lines += ["", "## EMPILÉ ×2 (exposition moyenne ~11 %)", ""]
    lines += bloc(stack2, "EMPILÉ ×2", CAPITAL)
    lines += ["", "## ORACLE anti-liq (×2, plafond)", ""]
    lines += bloc(oracle, "ORACLE ×2", CAPITAL)

    # ——— LE REGISTRE DES LIQUIDATIONS — trade par trade, précis ———
    liqs = [t for t in stack2["trades"] if t["liq"]]
    if liqs:
        lines += ["", "## REGISTRE DES LIQUIDATIONS — où, quand, combien", "",
                  "| Stratégie | Symbole | Entrée | Prix d'entrée → prix de mort | "
                  "Liquidé le | Perte | Balance après |",
                  "|---|---|---|---|---|---|---|"]
        for t in liqs:
            lp = t.get("liq_price")
            if lp is None and t.get("entry"):
                # fallback : prix de mort théorique depuis le LEVIER RÉEL du
                # trade (fossile ronde 5 : l'ancien 100/3−0.5 en dur donnait
                # 32,83 % quel que soit le symbole — ~2× trop haut pour un
                # memecoin à 16,66 % de maintenance, et figeait pré-F-038)
                lp = t["entry"] * (1 + liq_move_for(
                    t["sym"], t.get("lev") or 3) / 100)
            lt = t.get("liq_ts")
            # PR-169 (P2) : le ternaire coupait la ligne markdown AVANT les
            # colonnes Perte/Balance dès que liq_ts existait (4 colonnes
            # sur 7, pas de pipe final)
            row_liq = (f"| {lt:%d/%m %H:%M} " if lt else "| — ")
            lines.append(
                f"| {t['strategy']} | {t['sym']} "
                f"| {t['entry_ts']:%d/%m %H:%M} "
                f"| ${t['entry']:,.4g} → ${lp:,.4g} "
                f"{row_liq}"
                f"| **-${t['margin']:,.2f}** | ${t['balance']:,.2f} |")
        by_strat: dict[str, list] = {}
        for t in liqs:
            by_strat.setdefault(t["strategy"], []).append(t)
        lines += ["", "### Par stratégie", ""]
        for s, tl in sorted(by_strat.items()):
            loss = sum(x["margin"] for x in tl)
            hours = [ (x["liq_ts"] - x["entry_ts"]).total_seconds()/3600
                      for x in tl if x["liq_ts"] ]
            hm = f", mort après {np.mean(hours):.1f} h en moyenne" if hours else ""
            lines.append(f"- **{s}** : {len(tl)} liquidations, "
                         f"perte cumulée **${loss:,.2f}**{hm}")

    # --- la table mensuelle de l'EMPILÉ ×2 + garde-fous ---
    mrows = monthly_rows(stack2["trades"], CAPITAL)
    if not mrows:
        lines += ["", "## Aucun trade ce soir — pas de table mensuelle.",
                  "", "## VERDICT", "",
                  "- pas de données : vérifier le fetch nocturne des klines"]
        out = REPORTS / f"stacked-portfolio-{datetime.now(timezone.utc):%Y-%m-%d}.md"
        REPORTS.mkdir(exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("[stack] aucun trade — klines absentes ? vérifier le fetch")
        return 0
    prod = 1.0
    for r in mrows:
        prod *= (1 + r["roi"] / 100)
    gap = abs(prod - stack2["balance"] / CAPITAL)
    sum_pnl = sum(r["pnl"] for r in mrows)
    pnl_gap = abs(sum_pnl - (stack2["balance"] - CAPITAL))
    rois_m = [r["roi"] for r in mrows]
    neg = sum(1 for x in rois_m if x < 0)
    lines += ["", "## BLOC STATS DE CONCLUSION — EMPILÉ ×2", "",
              "| Stat | Valeur |", "|---|---|",
              f"| Wallet initial → final | ${CAPITAL:,.0f} → **${stack2['balance']:,.2f}** |",
              f"| ROI (1 an) | {(stack2['balance']/CAPITAL-1)*100:+.1f} % |",
              f"| ROI mensuel moyen | {np.mean(rois_m):+.1f} % "
              f"(pire {min(rois_m):+.1f} %, {neg} mois négatifs) |",
              f"| Max drawdown | {stack2['max_dd']:.1f} % "
              f"(creux ${stack2['trough']:,.2f}) |",
              f"| Trades / WR | {stack2['n']} / {stack2['n_wins']/max(stack2['n'],1)*100:.1f} % |",
              f"| Liquidations | {stack2['n_liq']} "
              f"({stack2['n_liq']/max(stack2['n'],1)*100:.1f} %) |",
              f"| Garde-fou composé des mois | écart {gap*100:.3f} % "
              f"{'OK' if gap < 0.005 else '✗ BUG'} |",
              f"| Garde-fou somme PnL | écart ${pnl_gap:.4f} "
              f"{'OK' if pnl_gap < 0.01 else '✗ BUG'} |",
              "", "### EMPILÉ ×2 — ROI par mois", "",
              "| Mois | Trades | WR | Liq | Balance début → fin | ROI mois |",
              "|---|---|---|---|---|---|"]
    for r in mrows:
        lines.append(
            f"| {r['month']} | {r['n']} | {r['w']/max(r['n'],1)*100:.0f} % "
            f"| {r['liq']} | ${r['start']:,.0f} → ${r['end']:,.0f} "
            f"| {r['roi']:+.1f} % |")

    # --- le verdict : l'empilage bat-il les parties ? ---
    dd_flat = alone["cascade"]["max_dd"]
    roi_sum = sum(alone[s]["balance"] for s in alone) / 3  # moyenne des seuls
    lines += ["", "## VERDICT", "",
              f"- DD cascade seule : {dd_flat:.1f} % → empilé ×1 : "
              f"{stack['max_dd']:.1f} %, empilé ×2 : {stack2['max_dd']:.1f} %",
              f"- Si l'empilé ×1 garde un DD ≪ la cascade seule à ROI "
              f"comparable, le re-lever devient possible : c'est la frontière.",
              f"- L'oracle ×2 ({oracle['balance']/CAPITAL*100:+.0f} %) reste "
              f"le plafond absolu."]

    out = REPORTS / f"stacked-portfolio-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[stack] cascade {counts['cascade']} / fdiv {counts['funding_div']} / "
          f"conf {counts['confluence']} évts")
    for lbl, r in (("cascade seule", alone["cascade"]),
                   ("fdiv seule", alone["funding_div"]),
                   ("conf seule", alone["confluence"]),
                   ("EMPILÉ ×1", stack), ("EMPILÉ ×2", stack2),
                   ("ORACLE ×2", oracle)):
        print(f"[stack] {lbl}: ${r['balance']:,.2f} "
              f"(ROI {(r['balance']/CAPITAL-1)*100:+.1f} %, "
              f"DD {r['max_dd']:.1f} %, liq {r['n_liq']})")
    print(f"[stack] garde-fous : composé écart {gap*100:.3f} %, "
          f"PnL écart ${pnl_gap:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
