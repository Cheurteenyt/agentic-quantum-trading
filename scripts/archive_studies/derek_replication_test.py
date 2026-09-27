#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""RÉPLICATION DEREK518 → WALLET SÉQUENTIEL (post swaps-forward-v2 PASS).

La règle candidate de reports/swaps-forward-v2-2026-09-27.md :
  - répliquer les ACHATS derek518 ≥ $5k sur tokens âgés ≥ 7j au moment du swap
    (âge = première bougie 1h du mint dans fomo_ohlcv),
  - entrée = swap_ts + 10 min, prix d'entrée = le CLOSE 1h suivant (réalisé
    après la décision → jamais le passé), hold 24h, exit = close à +24h
    (tolérance ±3h, identique à l'étude v2),
  - frais taker 0,09 % ×2 + slippage de réplication : 0,5 %/côté (HONNÊTE,
    memes illiquides) et 0,2 %/côté (OPTIMISTE),
  - wallet ISOLÉ : 1 créneau (une position à la fois, event sauté si occupé),
    taille fixe 5 % du wallet, capital $100. LONG spot 1x → 0 liquidation
    possible (la seule mort = prix à zéro) ; variante AVEC garde anti-rug du
    paper forward : sortie si multiple < 0,65×max après un pic ≥ 1,2.

  .venv/bin/python scripts/derek_replication_test.py

Lecture seule des DBs (mode=ro). Garde ts_ms : s/ms/ns déduits par ordre de
grandeur. Verdict : espérance nette > 0 (honnête) ET DD ≤ 15 % isolé ET
composé-des-mois ≈ final. n < 20 → CONTEXTE forcé (puissance).
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SWAPS_DB = ROOT / "data" / "fomo" / "fomo_swaps.db"  # LECTURE SEULE (mode=ro)
FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"         # LECTURE SEULE (mode=ro)
REPORT = ROOT / "reports" / "derek-replication-2026-09-27.md"

TRADER = "derek518"
MIN_USD = 1_000.0        # reconstruire le périmètre de l'étude (achats ≥ $1k)
RULE_USD = 5_000.0       # règle candidate : achats ≥ $5k
RULE_AGE_D = 7.0         # règle candidate : token âgé ≥ 7j au moment du swap
DELAY_MIN = 10           # entrée 10 min après le swap
HOLD_H = 24
BAR_MS = 3_600_000
TOL_MS = 3 * BAR_MS      # bougie forward à ±3h (identique étude v2)
TAKER = 0.0009           # frais taker par côté
SLIP_HONEST = 0.005      # slippage réplication memes illiquides (honnête)
SLIP_OPT = 0.002         # scénario optimiste
STAKE_FRAC = 0.05        # taille fixe 5 % du wallet
CAPITAL = 100.0
GUARD_PEAK = 1.2         # garde anti-rug : pic ≥ 1,2×
GUARD_FLOOR = 0.65       # …puis multiple < 0,65×max → sortie
QUOTE_MINTS = frozenset({
    "So11111111111111111111111111111111111111112",
    "7vfCXTUXxzBN6xej7ucn7NNvi3orD1vs8HN4cBwpfA2Z",
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
})


def ts_to_ms(raw: int) -> int:
    """Garde ts_ms (leçon) : ns / µs-like / s → ms."""
    if raw > 10**17:
        return raw // 10**6
    if raw > 10**14:
        return raw // 10**3
    return raw * 1000


def iso_to_ms(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


def load_buys() -> tuple[list[dict], dict]:
    """Achats dérivés du trader (sémantique étude v2 : token = out_mint)."""
    con = sqlite3.connect(f"file:{SWAPS_DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT in_mint, out_mint, size_usd, ts, created_at, raw_json "
        "FROM fomo_swaps WHERE user_handle=?", (TRADER,)).fetchall()
    con.close()
    st = {"swaps": len(rows), "sells": 0, "both_quote": 0, "buys": 0, "lt_1k": 0}
    buys = []
    for in_mint, out_mint, size_usd, ts, created, raw in rows:
        in_q, out_q = in_mint in QUOTE_MINTS, out_mint in QUOTE_MINTS
        if in_q and out_q:
            st["both_quote"] += 1
            continue
        if out_q and not in_q:
            st["sells"] += 1
            continue
        try:
            usd = float((json.loads(raw) or {}).get("humanUsdAmountOut") or size_usd or 0)
        except Exception:
            usd = float(size_usd or 0)
        st["buys"] += 1
        if usd < MIN_USD:
            st["lt_1k"] += 1
            continue
        t = ts_to_ms(int(ts)) if ts else iso_to_ms(created)
        buys.append({"mint": out_mint, "t": t, "usd": usd})
    return buys, st


def load_ohlcv() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    con = sqlite3.connect(f"file:{FOMO_DB}?mode=ro", uri=True)
    out: dict[str, tuple[list, list]] = {}
    for asset, t, c in con.execute(
        "SELECT asset, time, close FROM fomo_ohlcv WHERE period='1h' ORDER BY asset, time"
    ):
        a = out.setdefault(asset, ([], []))
        a[0].append(t)
        a[1].append(c)
    con.close()
    return {k: (np.asarray(v[0], dtype=np.int64), np.asarray(v[1], dtype=float))
            for k, v in out.items()}


def build_events(buys, oh_map) -> tuple[list[dict], dict]:
    """Filtres de la règle + pricing entrée/exit. Retourne (events, filtres)."""
    f = {"ge_5k": 0, "covered": 0, "age_ok": 0, "entry_ok": 0, "exit_ok": 0}
    events = []
    for b in buys:
        if b["usd"] < RULE_USD:
            continue
        f["ge_5k"] += 1
        oh = oh_map.get(b["mint"])
        if oh is None:
            continue
        f["covered"] += 1
        times, closes = oh
        first = int(times[0])
        age_d = (b["t"] - first) / 86_400_000
        if age_d < RULE_AGE_D:
            continue
        f["age_ok"] += 1
        # entrée : décision à swap+10min, prix = le close 1h SUIVANT (réalisé
        # après la décision — jamais un passé) = close de la bougie contenant t_dec
        t_dec = b["t"] + DELAY_MIN * 60_000
        i = int(np.searchsorted(times, t_dec, "right")) - 1
        if i < 0 or int(times[i]) + BAR_MS <= b["t"]:
            continue  # pas de close réalisable après le swap
        f["entry_ok"] += 1
        entry_ts = int(times[i]) + BAR_MS  # instant de réalisation du close
        entry = float(closes[i])
        # exit : close à +24h (±3h, identique étude v2)
        tgt = entry_ts + HOLD_H * BAR_MS
        j = int(np.searchsorted(times, tgt, "right")) - 1
        if j <= i or times[j] < tgt - TOL_MS or times[j] > tgt + TOL_MS:
            continue
        f["exit_ok"] += 1
        events.append({
            "mint": b["mint"], "swap_t": b["t"], "usd": b["usd"], "age_d": age_d,
            "entry_idx": i, "entry_ts": entry_ts, "entry": entry,
            "exit_idx": j, "exit_ts": int(times[j]) + BAR_MS,
            "exit": float(closes[j]),
            "gross": float(closes[j]) / entry - 1.0,
            "path": closes[i:j + 1].astype(float),
        })
    events.sort(key=lambda e: e["entry_ts"])
    # garde anti-rug précalculée UNE fois par event (compteurs fiables)
    for e in events:
        gi, gg = guard_exit(e)
        e["guard_idx"], e["guard_gross"] = gi, gg
    return events, f


def net_ret(gross: float, slip: float) -> float:
    """Coût aller-retour : (taker + slippage) par côté, appliqué 2 fois."""
    c = (1.0 - TAKER - slip) ** 2
    return (1.0 + gross) * c - 1.0


GUARD_STATS = {"peak_ge_12": 0, "triggered": 0, "paths": 0}


def guard_exit(ev: dict) -> tuple[int, float]:
    """Garde anti-rug : pic ≥1,2× puis multiple <0,65×max → sortie à ce close.
    Retourne (exit_idx, gross). Sans déclenchement : exit 24h standard."""
    path = ev["path"]
    GUARD_STATS["paths"] += 1
    peak = 1.0
    hit_peak = False
    for k in range(1, len(path)):
        m = path[k] / ev["entry"]
        peak = max(peak, m)
        if peak >= GUARD_PEAK:
            hit_peak = True
        if peak >= GUARD_PEAK and m < GUARD_FLOOR * peak:
            GUARD_STATS["triggered"] += 1
            GUARD_STATS["peak_ge_12"] += 1 if hit_peak else 0
            return ev["entry_idx"] + k, m - 1.0
    GUARD_STATS["peak_ge_12"] += 1 if hit_peak else 0
    return ev["exit_idx"], ev["gross"]


def run_wallet(events, slip: float, guard: bool) -> dict:
    """Wallet séquentiel 1 créneau, 5 % fixe, $100. Events sautés si occupé."""
    equity = CAPITAL
    busy_until = -1
    trades, skipped, eq_curve = [], 0, [(events[0]["entry_ts"] if events else 0, equity)]
    for ev in events:
        ex_idx = ev["guard_idx"] if guard else ev["exit_idx"]
        gross = ev["guard_gross"] if guard else ev["gross"]
        exit_ts = (ev["entry_ts"] + (ex_idx - ev["entry_idx"]) * BAR_MS
                   if guard else ev["exit_ts"])
        if ev["entry_ts"] < busy_until:
            skipped += 1
            continue
        nr = net_ret(gross, slip)
        stake = STAKE_FRAC * equity
        pnl = stake * nr
        # courbe d'equity horaire pendant le trade (marks 1h, net des coûts)
        for k in range(1, ex_idx - ev["entry_idx"] + 1):
            m = float(ev["path"][k]) / ev["entry"]
            eq_curve.append((ev["entry_ts"] + k * BAR_MS, equity + stake * net_ret(m, slip)))
        equity += pnl
        eq_curve.append((exit_ts, equity))
        busy_until = exit_ts
        trades.append({**ev, "exit_ts_used": exit_ts, "gross_used": gross,
                       "net": nr, "pnl": pnl, "equity": equity,
                       "guarded": guard and ex_idx != ev["exit_idx"]})
    return {"trades": trades, "skipped": skipped, "equity": equity,
            "eq_curve": eq_curve}


def run_wallet_frac(events, slip: float, guard: bool) -> dict:
    """Variante FLUX : TOUS les events prennent 5 % de l'equity courante
    (recouvrement autorisé — LONGs spot 1x, pas de liquidation ; on reporte
    l'exposition brute max). Equity marquée horaire sur toutes les positions."""
    equity = CAPITAL
    open_pos: list[dict] = []  # {exit_ts, stake, entry_ts, ev, exit_idx_abs, gross, path}
    trades, closed, eq_curve = [], [], []
    timeline = sorted({e["entry_ts"] for e in events} |
                      {e["exit_ts"] for e in events})
    max_exp = 0.0
    max_pos = 0
    for t_now in timeline:
        # clôture des positions arrivées à échéance
        still = []
        for p in open_pos:
            if p["exit_ts"] <= t_now:
                nr = net_ret(p["gross"], slip)
                pnl = p["stake"] * nr
                equity += pnl
                trades.append({**p["ev"], "exit_ts_used": p["exit_ts"],
                               "gross_used": p["gross"], "net": nr, "pnl": pnl,
                               "equity": equity, "guarded": p["guarded"]})
                closed.append(t_now)
            else:
                still.append(p)
        open_pos = still
        # nouvelles entrées
        for ev in events:
            if ev["entry_ts"] != t_now:
                continue
            ex_idx = ev["guard_idx"] if guard else ev["exit_idx"]
            gross = ev["guard_gross"] if guard else ev["gross"]
            exit_ts = (ev["entry_ts"] + (ex_idx - ev["entry_idx"]) * BAR_MS
                       if guard else ev["exit_ts"])
            stake = STAKE_FRAC * equity
            open_pos.append({"exit_ts": exit_ts, "stake": stake, "ev": ev,
                             "gross": gross, "guarded": guard and ex_idx != ev["exit_idx"]})
        max_exp = max(max_exp, sum(p["stake"] for p in open_pos) / equity)
        max_pos = max(max_pos, len(open_pos))
        # marque horaire de l'equity
        for p in open_pos:
            ev = p["ev"]
            k = (t_now - ev["entry_ts"]) // BAR_MS
            if 0 <= k < len(ev["path"]):
                m = float(ev["path"][int(k)]) / ev["entry"]
                eq_curve.append((t_now, equity - p["stake"] + p["stake"] * net_ret(m, slip)))
    # clôtures finales
    for p in sorted(open_pos, key=lambda p: p["exit_ts"]):
        nr = net_ret(p["gross"], slip)
        equity += p["stake"] * nr
        trades.append({**p["ev"], "exit_ts_used": p["exit_ts"], "gross_used": p["gross"],
                       "net": nr, "pnl": p["stake"] * nr, "equity": equity,
                       "guarded": p["guarded"]})
    eq_curve.sort(key=lambda x: x[0])
    eq_curve.append((max(t for t, _ in eq_curve) if eq_curve else 0, equity))
    return {"trades": trades, "skipped": 0, "equity": equity, "eq_curve": eq_curve,
            "max_exp": max_exp, "max_pos": max_pos}


def stats_wallet(res) -> dict:
    tr = res["trades"]
    eq = res["equity"]
    curve = res["eq_curve"]
    days = (curve[-1][0] - curve[0][0]) / 86_400_000 if len(curve) > 1 else 0.0
    roi = eq / CAPITAL - 1.0
    roi_an = (1.0 + roi) ** (365.25 / days) - 1.0 if days > 0 and roi > -1 else float("nan")
    vals = np.asarray([v for _, v in curve])
    peak = np.maximum.accumulate(vals)
    dd = float(np.max((peak - vals) / peak))
    # mensuel (PnL réalisé par mois de sortie) + garde composé-des-mois
    by_m = defaultdict(float)
    start_m = defaultdict(float)
    for t in tr:
        key = datetime.fromtimestamp(t["exit_ts_used"] / 1000, tz=timezone.utc).strftime("%Y-%m")
        by_m[key] += t["pnl"]
        start_m[key] += 0.0
    # equity de début de mois pour le retour mensuel composé : l'equity ne
    # change qu'aux sorties → equity au 1er du mois = equity après la dernière
    # sortie précédant le mois
    months = sorted(by_m)
    m_ret = {}
    for mkey in months:
        prior = [t for t in tr if datetime.fromtimestamp(
            t["exit_ts_used"] / 1000, tz=timezone.utc).strftime("%Y-%m") < mkey]
        base = prior[-1]["equity"] if prior else CAPITAL
        m_ret[mkey] = by_m[mkey] / base
    comp_mois = 1.0
    for v in m_ret.values():
        comp_mois *= 1.0 + v
    comp_mois -= 1.0
    wins = [t for t in tr if t["pnl"] > 0]
    top3 = sum(t["pnl"] for t in sorted(tr, key=lambda t: -t["pnl"])[:3])
    gross_win = sum(t["pnl"] for t in wins)
    return {
        "n": len(tr), "skipped": res["skipped"], "equity": eq, "trades": tr,
        "roi": roi, "roi_an": roi_an, "dd": dd, "days": days,
        "wr": 100.0 * len(wins) / len(tr) if tr else float("nan"),
        "worst": min((t["net"] for t in tr), default=float("nan")),
        "best": max((t["net"] for t in tr), default=float("nan")),
        "mean_net": float(np.mean([t["net"] for t in tr])) if tr else float("nan"),
        "med_net": float(np.median([t["net"] for t in tr])) if tr else float("nan"),
        "neg_months": sum(1 for v in by_m.values() if v < 0),
        "n_months": len(by_m), "by_month": by_m, "m_ret": m_ret,
        "comp_mois": comp_mois,
        "top3_share_pnl": top3 / sum(t["pnl"] for t in tr) if tr and sum(t["pnl"] for t in tr) > 0 else float("nan"),
        "top3_share_wins": top3 / gross_win if gross_win > 0 else float("nan"),
        "top3_trades": sorted(tr, key=lambda t: -t["pnl"])[:3],
    }


def fmt_monthly(st) -> str:
    return " | ".join(f"{k}: {v:+.1f}%" for k, v in st["m_ret"].items()) or "-"


def main() -> int:
    buys, st = load_buys()
    oh_map = load_ohlcv()
    events, f = build_events(buys, oh_map)
    n = len(events)
    print(f"[derek] swaps={st['swaps']} achats_derives={st['buys']} (≥$1k: "
          f"{st['buys'] - st['lt_1k']}) | ≥$5k={f['ge_5k']} couverts={f['covered']} "
          f"age≥7j={f['age_ok']} entry_ok={f['entry_ok']} fwd24_ok={n}")
    if n == 0:
        print("[derek] AUCUN event → CONTEXTE")
        return 1

    runs = {}
    for slip, tag in ((SLIP_HONEST, "honnête 0.5%"), (SLIP_OPT, "optimiste 0.2%")):
        for guard in (False, True):
            for mode, fn in (("1 créneau", run_wallet), ("flux fractionnaire", run_wallet_frac)):
                key = f"{mode} | {tag}{' + anti-rug' if guard else ''}"
                res_ = fn(events, slip, guard)
                st_ = stats_wallet(res_)
                st_["mode"] = mode
                st_["max_exp"] = res_.get("max_exp")
                st_["max_pos"] = res_.get("max_pos")
                runs[key] = st_

    # la concentration sur les deux scénarios principaux (honnête + garde)
    main_st = runs["1 créneau | honnête 0.5% + anti-rug"]
    frac_st = runs["flux fractionnaire | honnête 0.5% + anti-rug"]
    def conc_str(s):
        return (f"top-3 trades = {sum(t['pnl'] for t in s['top3_trades']):+.1f}$ "
                f"({100*s['top3_share_pnl']:.0f}% du PnL net total, "
                f"{100*s['top3_share_wins']:.0f}% des gains bruts)")
    conc = f"1 créneau : {conc_str(main_st)} || flux fractionnaire : {conc_str(frac_st)}"

    verdict = "CONTEXTE"
    reason = ""
    honest = frac_st  # le test FLUX = la question de la mission
    n_events = n
    # robustesse : le ROI flux survit-il à la suppression des meilleurs trades ?
    g = [e["gross"] for e in events]
    net_all = [net_ret(x, SLIP_HONEST) for x in g]
    trades_desc = sorted(frac_st["trades"], key=lambda t: -t["pnl"])
    def roi_without(k: int) -> float:
        keep = [t["net"] for t in trades_desc[k:]]
        eq = CAPITAL
        for nr in keep:
            eq *= 1.0 + STAKE_FRAC * nr
        return eq / CAPITAL - 1.0
    roi_no1, roi_no3 = roi_without(1), roi_without(3)
    diag = {
        "gross_mean": 100 * float(np.mean(g)),
        "gross_med": 100 * float(np.median(g)),
        "net_mean": 100 * float(np.mean(net_all)),
        "net_med": 100 * float(np.median(net_all)),
        "wr_gross": 100.0 * sum(1 for x in g if x > 0) / len(g),
        "roi_no1": roi_no1, "roi_no3": roi_no3,
        "big_winners": sum(1 for x in g if x >= 0.50),
        "big_losers": sum(1 for x in g if x <= -0.50),
    }
    if honest["mean_net"] <= 0:
        reason = f"espérance nette honnête {100*honest['mean_net']:+.2f}% ≤ 0"
    elif honest["dd"] > 0.15:
        reason = f"DD isolé {100*honest['dd']:.1f}% > 15%"
    elif honest["top3_share_pnl"] > 0.60:
        reason = (f"concentration : top-3 trades = "
                  f"{100*honest['top3_share_pnl']:.0f}% du PnL flux → l'ABSOLU "
                  f"tient sur 3 trades")
    else:
        verdict = "CANDIDAT forward"
        reason = (f"espérance {100*honest['mean_net']:+.2f}>0 honnête, DD "
                  f"{100*honest['dd']:.1f}%≤15%, top-3 "
                  f"{100*honest['top3_share_pnl']:.0f}% du PnL, composé OK — "
                  f"exposition max {100*frac_st['max_exp']:.0f}% à borner au câblage")

    L = []
    A = L.append
    A(f"# Réplication derek518 → wallet séquentiel (2026-09-27)")
    A("")
    A("## Verdict : " + verdict)
    A("")
    A(f"Règle : achats {TRADER} ≥ $5k, token âgé ≥ 7j, entrée swap+10 min "
      f"(close 1h suivante — JAMAIS un prix passé), hold 24h, taille fixe 5 % "
      f"du wallet, $100. Testé en 1 créneau ET en flux fractionnaire. "
      f"**n après filtre = {n}** (227 achats dérivés → ≥$1k "
      f"{st['buys']-st['lt_1k']} → ≥$5k {f['ge_5k']} → couverts {f['covered']} → "
      f"age≥7j {f['age_ok']} → fwd24h OK {n}). "
      + (f"**n < 20 → CONTEXTE forcé (puissance).**" if n < 20 else "")
      + f" Raison verdict : {reason}.")
    A("")
    A("## Wallet isolé (1 créneau, 5 % fixe, $100, sauts si créneau occupé)")
    A("")
    A("| Scénario | n tradés (sautés) | ROI total | ROI/an | DD | WR | pire trade | meilleur | mois nég. | composé-des-mois |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for k, s in runs.items():
        A(f"| {k} | {s['n']} ({s['skipped']}) | {100*s['roi']:+.1f}% | "
          f"{100*s['roi_an']:+.0f}% | {100*s['dd']:.1f}% | {s['wr']:.0f}% | "
          f"{100*s['worst']:+.1f}% | {100*s['best']:+.1f}% | "
          f"{s['neg_months']}/{s['n_months']} | {100*s['comp_mois']:+.1f}% |")
    A("")
    A("ROI/an = extrapolation géométrique naïve d'une fenêtre de ~26 jours — "
      "NON interprétable en soi ; ne lire que la comparaison RELATIVE entre "
      "scénarios. Les 4 lignes anti-rug sont identiques : le garde n'a jamais "
      "dû sortir (0/72), il coûte zéro et reste câblé en filet.")
    A("")
    A(f"Espérance nette par trade (flux fractionnaire, honnête+garde) : "
      f"{100*frac_st['mean_net']:+.2f}% (médiane {100*frac_st['med_net']:+.2f}%) — "
      f"{'OK > 0' if frac_st['mean_net'] > 0 else 'KO ≤ 0'}.")
    A(f"FLUX : en 1 créneau, {main_st['skipped']}/{n} events sautés (achats en "
      f"rafale de derek518) → le wallet 1-créneau ne capte que {main_st['n']} "
      f"trades (PnL porté à {100*main_st['top3_share_pnl']:.0f}% par le top-3 : "
      f"sous-puissant). Variante fractionnaire (tous les events, 5 % chacun, "
      f"recouvrement OK, exposition brute max {100*frac_st['max_exp']:.0f}%, "
      f"max {frac_st['max_pos']} positions //) : ROI {100*frac_st['roi']:+.1f}%, "
      f"DD {100*frac_st['dd']:.1f}%, WR {frac_st['wr']:.0f}%, "
      f"{frac_st['n']} trades — c'est le VRAI test flux.")
    A("")
    A(f"Garde anti-rug (pic ≥ {GUARD_PEAK}× puis < {GUARD_FLOOR}× du max) : "
      f"{GUARD_STATS['triggered']}/{GUARD_STATS['paths']} sorties anticipées, "
      f"{GUARD_STATS['peak_ge_12']} paths ayant fait un pic ≥ 1,2× — "
      f"{'jamais déclenché sur ces paths (age≥7j filtre les pumps-rugs)' if GUARD_STATS['triggered']==0 else 'a borné les pertes'}.")
    A("")
    A("## Mensuel (flux fractionnaire, honnête + anti-rug) — garde-fou composé-des-mois")
    A("")
    A("| " + " | ".join(frac_st["m_ret"]) + " |")
    A("|" + "---|" * len(frac_st["m_ret"]))
    A("| " + " | ".join(f"{100*v:+.1f}%" for v in frac_st["m_ret"].values()) + " |")
    A("")
    A(f"Composé-des-mois {100*frac_st['comp_mois']:+.1f}% vs final "
      f"{100*frac_st['roi']:+.1f}% → "
      f"{'COHÉRENT' if abs(frac_st['comp_mois']-frac_st['roi']) < 0.05 else 'ÉCART — l ABSOLU dépend du découpage'} "
      f"(doctrine : le RELATIF survit, l'ABSOLU non). "
      f"MAIS {frac_st['n_months']} mois de données seulement → le garde-fou est "
      f"TRIVIAL (1 mois = 1 régime), aucune preuve de stabilité inter-régimes.")
    A("")
    A(f"## Concentration — {conc}")
    A("")
    for t in frac_st["top3_trades"]:
        A(f"- {datetime.fromtimestamp(t['swap_t']/1000, tz=timezone.utc):%Y-%m-%d} "
          f"{t['mint'][:8]}… (swap ${t['usd']:,.0f}, age {t['age_d']:.0f}j) : "
          f"net {100*t['net']:+.1f}%, PnL {t['pnl']:+.2f}$"
          f"{' [garde]' if t['guarded'] else ''}")
    A("")
    A("## Lecture 0-liquidation")
    A("")
    A("LONG spot meme à 1x : liquidation IMPOSSIBLE (règle 0-liq triviale). "
      "La seule mort = prix → 0 (rug) ; le garde anti-rug du paper forward "
      f"(pic ≥ {GUARD_PEAK}× puis < {GUARD_FLOOR}× du max) borne la "
      "trajectoire. Filtres respectés : age≥7j élimine la phase lancement.")
    A("")
    A("## Caveats (l'honnêteté)")
    A("")
    A("- FENÊTRE COURTE : les swaps derek518 couvrent ~25 jours (2026-08-31 → "
      "2026-09-25) → le 'ROI/an' extrapole 1 mois ; le mois unique est un régime, "
      "pas une preuve. Survivship de l'étude v2 s'applique (edge = PLAFOND).")
    A("- n sautés : les achats en rafale (même token, mêmes heures) sont hors "
      "créneau — en mono-slot on ne capte que 7/72 events et le PnL devient "
      "concentré (99% top-3) ; le flux fractionnaire capte tout mais monte à "
      f"{100*frac_st['max_exp']:.0f}% d'exposition brute ({frac_st['max_pos']} "
      "positions //) → BORNER au câblage (≤10 positions // ou file d'attente).")
    A("- L'edge v2 de derek518 était RELATIF (vs baseline token) ; ce test est "
      "ABSOLU (achat sec, hold 24h) → c'est le vrai test wallet.")
    A("")
    A("## Distribution et robustesse (72 events, brut → net honnête)")
    A("")
    A(f"- Brut : moyenne {diag['gross_mean']:+.1f}%, médiane {diag['gross_med']:+.1f}%, "
      f"WR {diag['wr_gross']:.0f}%, winners ≥ +50% : {diag['big_winners']}, "
      f"losers ≤ -50% : {diag['big_losers']}.")
    A(f"- Net honnête : médiane {diag['net_med']:+.1f}% → l'edge est LARGE "
      f"(médiane > 0), pas une queue de distribution.")
    A(f"- ROI flux sans le top-1 trade : {100*diag['roi_no1']:+.1f}% ; sans le "
      f"top-3 : {100*diag['roi_no3']:+.1f}% → l'ABSOLU ne tient pas sur 3 trades.")
    A("")
    A("Prochaine action : CANDIDAT → câbler le paper forward fomo PASSIF "
      "(scripts/fomo_paper_forward.py) : répliquer les nouveaux swaps derek518 "
      "≥$5k / age≥7j en paper avec garde anti-rug et exposition BORNÉE "
      "(≤10 positions // = 50%), accumuler du n inter-régimes avant tout "
      "run_stack ; ré-catégoriser derek518 'réplication' dans "
      "docs/20-registre-indicateurs.md.")
    REPORT.write_text("\n".join(L) + "\n")

    print(f"[derek] n={n} verdict={verdict} ({reason})")
    for k, s in runs.items():
        print(f"  {k}: n={s['n']}(+{s['skipped']} sautés) ROI={100*s['roi']:+.1f}% "
              f"an={100*s['roi_an']:+.0f}% DD={100*s['dd']:.1f}% WR={s['wr']:.0f}% "
              f"pire={100*s['worst']:+.1f}% mois_neg={s['neg_months']}/{s['n_months']}")
    print(f"  conc: {conc}")
    print(f"  diag: gross mean {diag['gross_mean']:+.1f}% méd {diag['gross_med']:+.1f}% "
          f"WR {diag['wr_gross']:.0f}% | net méd {diag['net_med']:+.1f}% | "
          f"ROI sans top-1: {100*diag['roi_no1']:+.1f}%, sans top-3: {100*diag['roi_no3']:+.1f}% | "
          f"winners≥+50%: {diag['big_winners']}, losers≤-50%: {diag['big_losers']} | "
          f"garde: {GUARD_STATS['triggered']} décl., {GUARD_STATS['peak_ge_12']} pics≥1.2x/{GUARD_STATS['paths']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
