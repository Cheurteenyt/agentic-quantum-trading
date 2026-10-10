#!/usr/bin/env python
"""LE SIMULATEUR DE PORTEFEUILLE — du signal à l'argent réel, mois par mois.

La stratégie : cascade accélérée short 20x, hold 24h, sans stop.
  - capital initial : $100 (défaut)
  - position sizing : % de la balance courante en marge par trade
  - levier 20x → notionnel = 20 × la marge
  - frais taker 4 bps / maker 2 bps par side ×2, slippage taker 10 bps/side
  - funding : taux réel du symbole × heures de détention × notionnel
    (le SHORT REÇOIT le funding quand le taux est positif)
  - liquidation : en CHEMIN (MAE ≥ 100/lev − maintenance) OU à la sortie

DEUX SIMULATIONS par run :
  1. RÉELLE   — tous les trades, liquidations en chemin appliquées
  2. ORACLE   — les trades qui se feraient liquider ne sont PAS pris
                (impossible en pratique : c'est le PLAFOND du signal,
                 la borne « ceux qui se font pas liquidé »)

GARDE-FOUS ANTI-BUG du ROI (affichés à chaque run) :
  - le bucketing mensuel se fait par l'heure de SORTIE (le pnl atterrit
    à la fermeture, pas à l'entrée)
  - produit des (1+ROI_mensuel) vs balance finale/capitale — écart > 0,5 %
    = BUG affiché
  - somme des PnL mensuels vs PnL total — écart > 0,01 $ = BUG affiché

  .venv/bin/python scripts/portfolio_sim.py --capital 100 --size 0.03 \
      --universe majors --maker
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.funding_series import funding_series_all  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
LEV = 20
FEE_BPS = 4        # taker par side
SLIP_BPS = 10      # slippage par side
MAKER_BPS = 2      # maker par side (GTX), slippage ~0
# Repli si le symbole est absent de liq_params (8 symboles sur 586, surtout
# des Synthetic : SCRUSDT, SIUSDT). On prend le maintMarginPercent le plus BAS
# observé (2,5 %) — un repli trop bas surestimerait la ligne de mort, donc
# sous-estimerait la liquidation, c'est-à-dire nous rendre optimistes.
MAINT_PCT = 2.5
HOLD_H = 24        # la détention en heures
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
LIQ_MOVE_PCT = 100 / LEV - MAINT_PCT   # repli seulement (cf. liq_move_for)

# FIX F-038 — la marge de maintenance N'EST PAS 0,5 % : c'est le
# maintMarginPercent RÉEL par symbole, lu dans liq_params (extraite
# d'exchangeInfo). Le durcâ était 5x trop petit sur les majeures (2,5 %),
# donc la ligne de mort était repoussée : à 20x 4,5 % au lieu de 2,5 %, et à
# 10x 9,5 % au lieu de 7,5 % — sous-comptage des liquidations d'un facteur
# ~2,2 à 20x. Le commentaire « approx » masquait une erreur d'un facteur 5.
# La table existe, est peuplée et liq_price.py la lisait déjà correctement :
# le dur ne venait pas d'une absence d'information mais d'une constante
# copiée. Cette fonction est la source UNIQUE (stacked_portfolio l'importe).
_LIQ_PARAMS: dict[str, tuple[float, float]] | None = None

# P1 (audit 2026-10-08 §27) : le repli de marge de maintenance était
# OPTIMISTE.
#
# `liq_move_for` retombait sur MAINT_PCT = 2,5 % pour tout symbole absent
# de `liq_params`. C'est la valeur RÉELLE de BTC/ETH/BNB, et elle est
# fausse pour presque tout le reste de l'univers :
#
#     ASTERUSDT  12,5 %   → repli 2,5 % : 10 points trop optimiste
#     memecoins   16,66 %  → repli 2,5 % : 14 points trop optimiste
#     pire       25,0 %   → repli 2,5 % : 22,5 points trop optimiste
#
# `distance = 100/L − mm` : une marge sous-estimée donne une distance de
# mort SURESTIMÉE, donc des trades qui « survivent » dans le backtest et
# qui se seraient liquidés. Le biais est systematically flatteur — c'est
# la pire direction possible pour un modèle de risque.
#
# Le repli devient donc PRUDENT : la plus haute marge observée dans la
# table (la plus conservatrice), jamais une constante plate. Et il est
# COMPTÉ, pour qu'un rapport puisse dire combien de trades reposaient sur
# une marge substituée.
#
# Le compteur couvre TROIS sites de substitution (r7) :
#   liq_move_for  — marge inconnue -> _maint_prudent() ;
#   lev_capped    — symbole absent OU max_leverage NULL -> _lev_prudent() ;
#   maint_for     — marge inconnue -> repli par catégorie explicite
#                   (the_machine._maint_of, full_arsenal_2 « Lev sûr »).
# Publication : portfolio_sim.main() écrit la ligne de garde-fou
# (replis_check()) dans le rapport et sur stdout.
LIQ_FALLBACK_COUNT = 0

# Positions dont le levier est non VIABLE à la marge du symbole
# (100/L ≤ maint) : liquidées à l'entrée. Cf. issue #202 (C-B4).
LIQ_NON_VIABLE = 0


def _maint_prudent() -> float:
    """La marge de maintenance la plus haute observée — le repli prudent.

    Si la table est VIDE (base absente), on rend `MAINT_PCT` et on le dit :
    au moins on ne prétend pas avoir une lecture de l'univers.
    """
    valeurs = [mm for mm, _ in liq_params().values() if mm is not None]
    return max(valeurs) if valeurs else MAINT_PCT


def liq_params() -> dict[str, tuple[float, float]]:
    """(maint_margin_pct, max_leverage) par symbole, lus dans liq_params."""
    global _LIQ_PARAMS
    if _LIQ_PARAMS is None:
        _LIQ_PARAMS = {}
        try:
            con = sqlite3.connect(KDB, timeout=60)
            for sym, mm, mx in con.execute(
                    "SELECT symbol, maint_margin_pct, max_leverage FROM liq_params"):
                if mm is not None:
                    _LIQ_PARAMS[sym] = (float(mm), float(mx) if mx is not None else 0.0)
            con.close()
        except sqlite3.Error:
            # une base absente ne doit pas tuer le run — mais le repli
            # PRUDENT s'appliquera à TOUS les symboles (cf. _maint_prudent),
            # et `liq_params()` étant vide, chaque trade sera compté dans
            # LIQ_FALLBACK_COUNT. Un run sur une base absente se VOIT donc.
            _LIQ_PARAMS = {}
    return _LIQ_PARAMS


def liq_move_for(symbol: str, lev: float) -> float:
    """Le mouvement adverse qui liquide CE symbole (100/L − maintMarginPercent).

    Symbole présent dans `liq_params` : `maintMarginPercent` vient
    d'`exchangeInfo` (donnée publique, réelle).
    Symbole ABSENT : repli PRUDENT (la plus haute marge observée), et
    `LIQ_FALLBACK_COUNT` est incrémenté. Un repli optimiste rendrait le
    modèle flatteur ; cf. le commentaire de `LIQ_FALLBACK_COUNT`.

    ⚠️ APPROXIMATION AU 1er PALIER (issue #212, P1 §27). `maintMarginPercent`
    est le taux du PREMIER bracket, pas le taux effectif de la position.
    Aster liquide par PALIERS de notionnel (`leverageBrackets`, avec `cum`) :
    au-delà du 1er palier, la marge de maintien requise augmente, donc la
    liquidation réelle arrive PLUS TÔT que ne le prédit cette formule — le
    modèle est légèrement OPTIMISTE à fort notionnel, jamais prudent.
    Les paliers ne sont pas dans ce dépôt : `GET /fapi/v3/leverageBrackets`
    est un endpoint SIGNÉ (testé : HTTP 400 / -1102 sans clé API wallet).
    Tant que la donnée manque, cette fonction reste une approximation :
    ne pas la présenter comme EXACTE dans un rapport, et ne pas en tirer
    une conclusion de risque sur des notionnels élevés.
    """
    global LIQ_FALLBACK_COUNT, LIQ_NON_VIABLE
    # lev <= 0 : un spec/event mal formé (lev: 0 ou négatif — écrit à la main
    # ou généré) ferait 100.0/lev -> ZeroDivisionError, tuant le run au lieu
    # de le compter. Un levier nul/négatif n'a aucun sens physique : la
    # position est « non exécutable ». On borne à 0 (« liquidé à l'entrée »,
    # même sémantique que le cas distance <= 0) et on compte, comme #202.
    # Bug trouvé par fuzz 2026-10-10 (liq_move_for("BTC", 0) -> ZeroDivision).
    if not lev or lev <= 0:
        LIQ_NON_VIABLE += 1
        return 0.0
    entree = liq_params().get(symbol)
    if entree is None:
        LIQ_FALLBACK_COUNT += 1
        mm = _maint_prudent()
    else:
        mm = entree[0]
    distance = 100.0 / lev - mm
    if distance <= 0.0:
        # Levier non VIABLE à cette marge : 100/L ≤ mm signifie que la
        # marge de maintenance exige à elle seule plus que le notionnel
        # entier du levier, donc la position est liquidée à l'ENTRÉE.
        #
        # C'est l'issue #202 (C-B4), restée LATENTE jusqu'ici parce que le
        # repli plat 2,5 % rendait le cas presque inatteignable. Le repli
        # PRUDENT le rend réel : un symbole à 25 % de marge de maintenance
        # est liquidé dès l'entrée à 10x, et le repli l'expose.
        #
        # Retourner une distance NÉGATIVE n'aurait aucun sens physique —
        # « liquidé il y a −15 % » n'est pas une mesure. On borne à 0,
        # ce qui signifie exactement « liquidé à l'entrée », et on compte.
        LIQ_NON_VIABLE += 1
        return 0.0
    return distance


def _lev_prudent() -> float:
    """Le plus BAS max_leverage observé — le repli prudent pour un symbole
    dont on ignore la contrainte. Un symbole inconnu est plafonné AU PIRE
    plutôt qu'au mieux : sous-compter des trades est réparable, simuler un
    ordre que l'échange refuse ne l'est pas."""
    valeurs = [mx for _, mx in liq_params().values() if mx and mx > 0]
    return min(valeurs) if valeurs else 1.0


def lev_capped(symbol: str, lev: float) -> float:
    """Le levier réellement exécutable : jamais au-dessus du max_leverage.

    75 symboles de l'univers ont max_leverage < 3 : à 3x ou 10x fixe l'ordre
    est refusé par Aster, et le trade était pourtant compté comme exécuté.

    Symbole ABSENT de `liq_params` : le plafond était **ignoré** — le
    `.get(symbol, (MAINT_PCT, 0.0))[1]` rendait 0, et `if mx > 0 else lev`
    renvoyait `lev` inchangé. C'est le défaut miroir de `liq_move_for` :
    là on surestimait la distance de mort, ici on surestimait le levier
    autorisé. Les deux font apparaître un trade exécutable qui ne l'est pas.

    Mesuré : **8 symboles de l'univers 1h** (586) n'ont aucune ligne dans
    `liq_params` — ACNUSD1, CTUSDT, METAUSD1, PAIDUSDT, QNTUSDT, SCRUSDT,
    SIUSDT, XDPUSDT. Ce n'est pas théorique.

    Deuxième trou (r7) : le cas `mx <= 0` — ligne PRÉSENTE mais
    max_leverage NULL (chargé 0.0, l.119) — retombait sur
    `return min(lev, mx) if mx > 0 else lev` et rendait `lev` INCHANGÉ :
    le plafond était ignoré ET le compteur muet, pour un défaut miroir
    de F-047 resté vivant après le fix des symboles absents.
    tests/test_f038_liq_maint.py:155 skippait explicitement ce chemin
    (`if mx <= 0: continue`) : aucun test ne le verrouillait.

    Repli : le plus BAS max_leverage observé, et `LIQ_FALLBACK_COUNT`
    incrémenté — une seule place de comptage, pour les absences ET les
    max_leverage inconnus.
    """
    global LIQ_FALLBACK_COUNT
    entree = liq_params().get(symbol)
    if entree is None or entree[1] <= 0:
        # absent OU max_leverage inconnu (NULL chargé 0.0) : le plafond
        # n'est pas une donnée. Repli prudent, et COMPTÉ — un run sur une
        # table trouée se voit désormais, au lieu de passer pour borné.
        LIQ_FALLBACK_COUNT += 1
        return min(lev, _lev_prudent())
    return min(lev, entree[1])


def maint_for(symbol: str, fallback: float) -> float:
    """La marge de maintenance du symbole, repli EXPLICITEMENT compté.

    Le `.get(symbol, (fallback, 0.0))[0]` en ligne donnait la bonne valeur
    en SILENCE : si `symbol` est absent de `liq_params`, le repli
    `fallback` nourrissait le calcul sans qu'aucun octet du rapport ne le
    dise. Trois replis de marge, zéro compteur : `_maint_of` de
    the_machine (MAINT_MAJORS/MAINT_MEME, lues au temps d'IMPORT), le
    « Lev sûr » de full_arsenal_2 (miroir exact du bug #213 corrigé dans
    liq_move_for, jamais porté là).

    Le repli reste la valeur PAR CATÉGORIE (2,5 majeures, 16,66 meme) —
    c'est le meilleur estimateur quand la catégorie est connue ; le repli
    PRUDENT global (_maint_prudent, max observé) serait FAUX pour la
    catégorie opposée. Seule la SUBSTITUTION est désormais comptée.
    """
    global LIQ_FALLBACK_COUNT
    entree = liq_params().get(symbol)
    if entree is None:
        LIQ_FALLBACK_COUNT += 1
        return float(fallback)
    return entree[0]


def replis_check() -> str:
    """La ligne de garde-fou du rapport : combien de lectures de
    marge/plafond ont reposé sur une SUBSTITUTION (pas une donnée).

    Compteurs lus au moment de l'appel — le rapport doit être écrit après
    les runs qui consomment liq_move_for/lev_capped/maint_for, sinon les
    compteurs ne reflètent que le début du process.
    """
    n = LIQ_FALLBACK_COUNT
    if n <= 0:
        return "replis marge/plafond substitués : 0 (OK)"
    return (f"replis marge/plafond substitués : {n} ⚠ ({n} lectures sans "
            f"donnée liq_params — marges/leviers de repli appliqués)")


def btc_regime_series() -> pd.Series:
    """Le régime BTC (tendance EMA7j × volatilité) aligné sur l'index BTC."""
    con = sqlite3.connect(KDB, timeout=60)
    btc = load_df(con, "BTCUSDT")
    con.close()
    if btc is None or len(btc) < 500:
        return pd.Series(dtype=str)
    close = btc["close"]
    trend = np.where(close > close.ewm(span=7, adjust=False).mean(),
                     "haussier", "baissier")
    atr = close.diff().abs().rolling(24).mean()
    vol = np.where(atr > atr.rolling(30 * 24, min_periods=100).median(),
                   "vol_haute", "vol_basse")
    return pd.Series([f"{t}/{v}" for t, v in zip(trend, vol)], index=btc.index)


def run_sim(events: list[dict], capital: float, size: float,
            funding_hourly: dict[str, float], fee_bps: int, slip_bps: int,
            oracle: bool = False, size_fn=None) -> dict:
    """La simulation séquentielle. oracle=True : les trades voués à la
    liquidation ne sont pas pris (plafond théorique, pnl=0, pas de frais).
    size_fn(e) -> taille (0-1) par trade : remplace le sizing fixe."""
    balance = capital
    peak = trough = balance
    max_dd = 0.0
    equity: list[tuple[int, float]] = []
    trades: list[dict] = []
    n = n_liq = n_wins = 0
    fees_tot = fund_tot = 0.0

    i = 0
    while i < len(events):
        e = events[i]
        if balance <= 1:
            break
        trade_size = size_fn(e) if size_fn is not None else size
        if trade_size <= 0:
            i += 1               # gated : le créneau est libéré pour le suivant
            continue
        margin_alloc = balance * trade_size
        notional = margin_alloc * LEV
        fees = notional * (fee_bps + slip_bps) / 10000 * 2
        # FIX lot2 (F3) : funding as-of — Σ des taux réels de (entrée, sortie],
        # plus jamais la moyenne full-sample × hold. Shim float : legacy RO.
        fser = funding_hourly.get(e["sym"])
        if fser is None:
            funding = 0.0
        elif hasattr(fser, "sum_pct_between"):
            _t0 = e["ts_ms"] / 1e6
            funding = notional * fser.sum_pct_between(
                _t0, _t0 + HOLD_H * 3_600_000.0) / 100.0
        else:
            funding = notional * fser / 100.0 * HOLD_H
        pnl = e["price_ret_short"] / 100 * notional + funding - fees

        liq = e["mae_adverse"] >= liq_move_for(e["sym"], LEV) or pnl <= -margin_alloc
        if liq and oracle:
            pnl = 0.0            # l'oracle n'a pas pris le trade
            liq = False
        elif liq:
            pnl = -margin_alloc
            n_liq += 1

        balance += pnl
        if not oracle:
            fees_tot += fees
            fund_tot += funding
        n += 1
        n_wins += pnl > 0

        peak = max(peak, balance)
        dd = (peak - balance) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
        trough = min(trough, balance)

        exit_ms = e["ts_ms"] + HOLD_H * 3600 * 10**9   # ts_ms = des NS (nom hérité)
        equity.append((exit_ms, balance))
        trades.append({
            "sym": e["sym"],
            "exit_ts": datetime.fromtimestamp(exit_ms / 10**9, tz=timezone.utc),
            "pnl": pnl, "balance": balance, "liq": liq,
        })
        hold_end = e["ts_ms"] + HOLD_H * 3600 * 10**9  # ts_ms = des NS (nom hérité)
        while i < len(events) and events[i]["ts_ms"] < hold_end:
            i += 1

    return {"balance": balance, "max_dd": max_dd, "trough": trough,
            "equity": equity, "trades": trades, "n": n, "n_liq": n_liq,
            "n_wins": n_wins, "fees": fees_tot, "funding": fund_tot}


def monthly_rows(trades: list[dict], capital: float) -> list[dict]:
    """Décomposition mensuelle par heure de SORTIE (le pnl atterrit là)."""
    rows: dict[str, dict] = {}
    for t in sorted(trades, key=lambda x: x["exit_ts"]):
        m = t["exit_ts"].strftime("%Y-%m")
        r = rows.setdefault(m, {"pnl": 0.0, "n": 0, "w": 0, "liq": 0,
                                "nonliq_n": 0, "nonliq_w": 0, "nonliq_pnl": 0.0})
        r["pnl"] += t["pnl"]
        r["n"] += 1
        r["w"] += t["pnl"] > 0
        r["liq"] += t["liq"]
        if not t["liq"]:
            r["nonliq_n"] += 1
            r["nonliq_w"] += t["pnl"] > 0
            r["nonliq_pnl"] += t["pnl"]
    out, bal = [], capital
    for m in sorted(rows):
        r = rows[m]
        start = bal
        bal += r["pnl"]
        out.append({"month": m, **r, "start": start, "end": bal,
                    "roi": (r["pnl"] / start * 100) if start > 0 else 0.0})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--size", type=float, default=0.05,
                    help="%% de la balance alloué en marge par trade")
    ap.add_argument("--universe", choices=["majors", "all"], default="majors")
    ap.add_argument("--maker", action="store_true",
                    help="fills maker-only (GTX) : 2 bps/side, 0 slippage")
    args = ap.parse_args()
    fee_bps, slip_bps = (MAKER_BPS, 0) if args.maker else (FEE_BPS, SLIP_BPS)

    con = sqlite3.connect(KDB, timeout=60)
    funding_hourly = funding_series_all(KDB)
    regime = btc_regime_series()
    # UN SEUL collecteur cascade (anti_liq) — la divergence des deux
    # collecteurs (warmup + features) produisait deux vérités (25/09)
    # import paresseux : anti_liq importe run_sim de ce module
    from scripts.anti_liq import collect_featured
    events = collect_featured(regime, args.universe)
    con.close()
    # le MONITEUR DE MARGE : la frontière 10x suppose un MAE max < 9,5 % —
    # si le MAE observé monte, le levier sûr baisse (règle : lev ≤ 100/(maxMAE+0,5))
    # il mesure la population GATED (celle qu'on trade réellement) — le gate
    # AL exclut les monstres de volatilité (MAE 13 % vus hors gate)
    from scripts.anti_liq import add_rolling_scores
    add_rolling_scores(events)
    thr = float(np.nanquantile(
        [e.get("al_score", float("nan"))
         for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= thr)]
    maes = [e["mae_adverse"] for e in gated]
    maes_raw = [e["mae_adverse"] for e in events]
    if maes:
        mae_max = max(maes)
        lev_safe = 100 / (mae_max + 0.5)
        print(f"[portfolio] MONITEUR MAE (gated, {len(gated)} trades) : "
              f"max {mae_max:.2f} % → levier sûr ≤ {lev_safe:.1f}x "
              f"{'OK — 10x tient' if lev_safe >= 10 else '⚠ LA MARGE 10x EST MORDUE — baisser le levier'}"
              f" (brut hors gate : max {max(maes_raw):.2f} % — le gate les exclut)")

    real = run_sim(events, args.capital, args.size, funding_hourly,
                   fee_bps, slip_bps, oracle=False)
    oracle = run_sim(events, args.capital, args.size, funding_hourly,
                     fee_bps, slip_bps, oracle=True)

    mrows = monthly_rows(real["trades"], args.capital)
    orows = monthly_rows(oracle["trades"], args.capital)
    if not mrows:
        out = REPORTS / f"portfolio-sim-{datetime.now(timezone.utc):%Y-%m-%d}.md"
        REPORTS.mkdir(exist_ok=True)
        out.write_text("# LE PORTEFEUILLE — aucun trade ce soir "
                       "(klines absentes ? vérifier le fetch nocturne)\n",
                       encoding="utf-8")
        print("[portfolio] aucun trade — klines absentes ? vérifier le fetch")
        return 0

    # --- GARDE-FOUS ANTI-BUG ---
    checks: list[str] = []
    prod_roi = 1.0
    for r in mrows:
        prod_roi *= (1 + r["roi"] / 100)
    gap = abs(prod_roi - real["balance"] / args.capital)
    checks.append(f"composé des mois vs final : écart {gap*100:.3f} % "
                  + ("OK" if gap < 0.005 else "✗ BUG"))
    sum_pnl = sum(r["pnl"] for r in mrows)
    pnl_gap = abs(sum_pnl - (real["balance"] - args.capital))
    checks.append(f"somme PnL mensuels vs total : écart ${pnl_gap:.4f} "
                  + ("OK" if pnl_gap < 0.01 else "✗ BUG"))
    # r7 : les compteurs de substitution, LUS APRÈS les runs (real +
    # oracle), publiés dans le rapport ET sur stdout. Avant, ils
    # n'étaient lus par AUCUN rapport — le commentaire « un run sur une
    # base absente se VOIT donc » était faux.
    checks.append(replis_check())

    def fmt_table(rows: list[dict], label: str) -> list[str]:
        ls = [f"### {label}", "",
              "| Mois | Trades | WR | Liq | Balance début → fin | ROI mois | ROI cumulé |",
              "|---|---|---|---|---|---|---|"]
        cap = args.capital
        for r in rows:
            cum = (r["end"] / cap - 1) * 100
            ls.append(
                f"| {r['month']} | {r['n']} | {r['w']/max(r['n'],1)*100:.0f} % "
                f"| {r['liq']} | ${r['start']:,.0f} → ${r['end']:,.0f} "
                f"| {r['roi']:+.1f} % | {cum:+.1f} % |")
        return ls

    pnls = [t["pnl"] for t in real["trades"]]
    exp_trade = sum(pnls) / len(pnls) if pnls else 0.0
    rois_m = [r["roi"] for r in mrows]
    neg_months = sum(1 for x in rois_m if x < 0)
    verdict = ("TRADEABLE — forward requis"
               if real["balance"] / args.capital > 1.2 and real["max_dd"] < 60
               and real["n"] >= 30 else "MARGINAL — à surveiller"
               if real["balance"] > args.capital and real["n"] >= 30
               else "NON TRADEABLE")

    lines = [
        "# LE PORTEFEUILLE — cascade accélérée short 20x, hold 24h",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — 1 an, "
        f"univers {args.universe}, "
        f"exécution {'MAKER (GTX)' if args.maker else 'TAKER'}, "
        f"sizing {args.size*100:.0f} %, capital ${args.capital:,.0f}.",
        "", "## GARDE-FOUS ANTI-BUG", "",
    ] + [f"- {c}" for c in checks] + [
        "", "## BLOC STATS DE CONCLUSION (RÉEL)", "",
        "| Stat | Valeur |", "|---|---|",
        f"| Wallet initial → final | ${args.capital:,.0f} → **${real['balance']:,.2f}** |",
        f"| **ROI (1 an)** | **{(real['balance']/args.capital-1)*100:+.1f} %** |",
        f"| ROI mensuel moyen | {np.mean(rois_m):+.1f} % "
        f"(pire {min(rois_m):+.1f} %, meilleur {max(rois_m):+.1f} %, "
        f"{neg_months} mois négatifs) |",
        f"| Trades / Winrate | {real['n']} / {real['n_wins']/max(real['n'],1)*100:.1f} % |",
        f"| Liquidations (en chemin) | {real['n_liq']} "
        f"({real['n_liq']/max(real['n'],1)*100:.1f} %) |",
        f"| Frais + slippage payés | ${real['fees']:,.2f} |",
        f"| Funding net (reçu +) | ${real['funding']:+,.2f} |",
        f"| Espérance / trade | ${exp_trade:+.2f} |",
        (f"| Meilleur / pire trade | ${max(pnls):+,.2f} / ${min(pnls):+,.2f} |"
         if pnls else "| Meilleur / pire trade | — |"),
        f"| Max drawdown | {real['max_dd']:.1f} % (creux ${real['trough']:,.2f}) |",
        f"| **VERDICT** | **{verdict}** |",
        "", f"## ORACLE ANTI-LIQUIDATION — le plafond « ceux qui se font pas liquidé »",
        f"", f"Les {real['n_liq']} trades que la sim RÉELLE liquide en chemin "
        f"ne sont pas pris ici (impossible en pratique) :",
        f"wallet ${args.capital:,.0f} → **${oracle['balance']:,.2f}** "
        f"(ROI {(oracle['balance']/args.capital-1)*100:+.1f} %), "
        f"DD {oracle['max_dd']:.1f} %, WR {oracle['n_wins']/max(oracle['n'],1)*100:.1f} %, "
        f"moyenne mensuelle "
        f"{np.mean([r['roi'] for r in orows]):+.1f} % "
        f"(pire {min(r['roi'] for r in orows):+.1f} %).",
        f"Sur les SEULS trades non liquidés (stat ex-post) : WR "
        f"{sum(1 for t in real['trades'] if not t['liq'] and t['pnl']>0)/max(sum(1 for t in real['trades'] if not t['liq']),1)*100:.1f} %, "
        f"pnl moyen ${sum(t['pnl'] for t in real['trades'] if not t['liq'])/max(sum(1 for t in real['trades'] if not t['liq']),1):+.2f}.",
    ] + fmt_table(mrows, "RÉEL — ROI par mois (bucketing par sortie)") \
      + [""] + fmt_table(orows, "ORACLE anti-liquidation — par mois") + [
        "", "Paramètres : levier 20x, "
        f"frais {(fee_bps+slip_bps)*2} bps RT sur notionnel "
        f"(= {(fee_bps+slip_bps)*2*LEV/100:.1f} % de marge), "
        f"liquidation en chemin à {liq_move_for('BTCUSDT', LEV):.1f} % adverse "
        f"(maintMarginPercent réel des majeures, liq_params), hold {HOLD_H}h.",
        "L'oracle anti-liquidation = un plafond, PAS une stratégie : personne",
        "ne sait ex ante quel trade sera liquidé. L'écart réel ↔ oracle = le",
        "coût exact des liquidations.",
    ]

    out = REPORTS / f"portfolio-sim-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[portfolio] {args.universe} "
          f"{'maker' if args.maker else 'taker'} size={args.size:.0%} : "
          f"RÉEL ${args.capital:,.0f}→${real['balance']:,.2f} "
          f"({(real['balance']/args.capital-1)*100:+.1f}%/an, "
          f"moy. mensuelle {np.mean(rois_m):+.1f}%, DD {real['max_dd']:.1f}%, "
          f"liq {real['n_liq']}) | ORACLE ${oracle['balance']:,.2f} "
          f"({(oracle['balance']/args.capital-1)*100:+.1f}%/an, "
          f"moy. mensuelle {np.mean([r['roi'] for r in orows]):+.1f}%)")
    for c in checks:
        print(f"[portfolio] garde-fou : {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
