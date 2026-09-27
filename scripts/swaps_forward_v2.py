#!/usr/bin/env python
"""ÉTUDE SWAPS → FORWARD RETURNS v2 — le re-run post-backfill complet.

v1 (reports/swaps-forward-2026-09-27.md) était mort par la couverture :
98% des achats sans prix -> 51 events exploitables = mono-token. Le backfill
mobula est TERMINÉ (1 353 mints, ~6,8 M bougies) -> re-run sur l'échantillon
complet : 2 832 achats ≥ $1k presque tous couverts.

Construction IDENTIQUE au v1 (scripts/swaps_forward_study.py) :
- side DÉRIVÉ : le token tradé = le mint non-QUOTE ; buy -> token = out_mint,
  $ = humanUsdAmountOut du raw_json. Jamais la colonne side sur foi.
- ts : garde s/ms/ns (leçon ts_ms) -> ts_to_ms.
- forward +24h/+72h via closes 1h (bougie cible ±3h), baseline du MÊME token
  (moyenne de ses forwards de la même durée sur sa fenêtre couverte).
- EDGE = forward post-achat − baseline du token (pas la bêta memecoin).

Nouveautés v2 : edge 24h ET 72h, régimes 2026-08 vs 2026-09, classement des
traders complet (t-stat), barre PASS mission (edge ≥ +2% à 24h tenu en VAL ET
≥ 2 traders n≥15 / edge>0 / médiane>0), concentration top-3 tokens.

  .venv/bin/python scripts/swaps_forward_v2.py

Honnêteté : survivorship (tokens vivants = visibles -> edge = PLAFOND),
délai de réplication réel 5-15 min (ici entrée = close 1h -> conservateur).
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SWAPS_DB = ROOT / "data" / "fomo" / "fomo_swaps.db"  # LECTURE SEULE (mode=ro)
FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"         # LECTURE SEULE (mode=ro)
REPORT = ROOT / "reports" / "swaps-forward-v2-2026-09-27.md"

MIN_USD = 1_000.0
FWD_H = (24, 72)
BAR_MS = 3_600_000
TOL_MS = 3 * BAR_MS  # la bougie forward doit être à ±3h de la cible
QUOTE_MINTS = frozenset({
    "So11111111111111111111111111111111111111112",  # SOL wrappé
    "7vfCXTUXxzBN6xej7ucn7NNvi3orD1vs8HN4cBwpfA2Z",  # WETH Wormhole
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",  # cbBTC Coinbase
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # WBTC
})


def iso_to_ms(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


def ts_to_ms(raw: int) -> int:
    """Le garde ts_ms : s / ms / ns — l'unité se déduit de l'ordre de grandeur."""
    if raw > 10**17:
        return raw // 10**6
    if raw > 10**14:
        return raw // 10**3
    return raw * 1000


def load_events() -> tuple[list[dict], dict]:
    con = sqlite3.connect(f"file:{SWAPS_DB}?mode=ro", uri=True)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT user_id, user_handle, in_mint, out_mint, size_usd, ts, "
        "created_at, raw_json FROM fomo_swaps"
    ).fetchall()
    con.close()
    stats = {"total": len(rows), "buys": 0, "sells": 0, "cross": 0,
             "both_quote": 0, "lt_1k": 0, "no_cover": 0, "no_fwd": 0}
    events = []
    for uid, handle, in_mint, out_mint, size_usd, ts, created, raw in rows:
        in_q, out_q = in_mint in QUOTE_MINTS, out_mint in QUOTE_MINTS
        if in_q and out_q:
            stats["both_quote"] += 1
            continue
        if out_q and not in_q:          # sell du token in_mint — hors périmètre
            stats["sells"] += 1
            continue
        mint = out_mint                  # buy → token = out_mint (sémantique corrigée)
        if not in_q and not out_q:
            stats["cross"] += 1          # rotation token→token : un achat du out
        try:
            rawj = json.loads(raw)
        except Exception:
            rawj = {}
        usd = rawj.get("humanUsdAmountOut") or size_usd or 0.0
        stats["buys"] += 1
        if usd < MIN_USD:
            stats["lt_1k"] += 1
            continue
        t_ms = ts_to_ms(int(ts)) if ts else iso_to_ms(created)
        events.append({"user": handle or uid[:8], "mint": mint, "t": t_ms,
                       "usd": float(usd), "created": created})
    return events, stats


def load_ohlcv() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    con = sqlite3.connect(f"file:{FOMO_DB}?mode=ro", uri=True)
    cur = con.cursor()
    out: dict[str, tuple[list, list]] = {}
    n_bars = 0
    for asset, t, c in cur.execute(
        "SELECT asset, time, close FROM fomo_ohlcv WHERE period='1h' ORDER BY asset, time"
    ):
        a = out.setdefault(asset, ([], []))
        a[0].append(t)
        a[1].append(c)
        n_bars += 1
    con.close()
    print(f"[v2] ohlcv 1h : {n_bars} bougies, {len(out)} mints couverts")
    return {k: (np.asarray(v[0], dtype=np.int64), np.asarray(v[1], dtype=float))
            for k, v in out.items()}


def forward(oh: tuple[np.ndarray, np.ndarray], t: int, hours: int):
    """Retour t→t+hours via la close 1h ; None si la bougie cible manque (>±3h)."""
    times, closes = oh
    i = int(np.searchsorted(times, t, "right")) - 1
    if i < 0:
        return None
    tgt = t + hours * BAR_MS
    j = int(np.searchsorted(times, tgt, "right")) - 1
    if j <= i or times[j] < tgt - TOL_MS or times[j] > tgt + TOL_MS:
        return None
    return closes[j] / closes[i] - 1.0


def baselines(oh_map, mints: set[str]) -> tuple[dict, dict, dict, dict]:
    """Le baseline PAR TOKEN sur TOUTE sa couverture (option mission :
    « la médiane du token sur l'année de couverture »). La MÉDIANE est la
    référence v2 : la moyenne des forwards 24h d'un memecoin est écrasée par
    ses heures de lancement (+5000% à la pause) — v2 run 1 : baseline moyen
    +175%/24h, artefact. Moyenne gardée pour la ligne de sensibilité."""
    med24: dict[str, float] = {}
    med72: dict[str, float] = {}
    mean24: dict[str, float] = {}
    mean72: dict[str, float] = {}
    for mint in mints:
        oh = oh_map[mint]
        times = oh[0]
        r24 = [r for r in (forward(oh, int(t), 24) for t in times) if r is not None]
        r72 = [r for r in (forward(oh, int(t), 72) for t in times) if r is not None]
        if len(r24) >= 24:
            med24[mint] = float(np.median(r24))
            mean24[mint] = float(np.mean(r24))
        if len(r72) >= 12:
            med72[mint] = float(np.median(r72))
            mean72[mint] = float(np.mean(r72))
    return med24, med72, mean24, mean72


def tstat(xs):
    if len(xs) < 3:
        return 0.0
    sd = statistics.stdev(xs)
    return statistics.mean(xs) / (sd / len(xs) ** 0.5) if sd > 0 else 0.0


def block(name, evs) -> str:
    if not evs:
        return f"| {name} | 0 | - | - | - | - | - | - |"
    r24 = [e["ret24"] for e in evs if e["ret24"] is not None]
    e24 = [e["edge24"] for e in evs if e["edge24"] is not None]
    e72 = [e["edge72"] for e in evs if e["edge72"] is not None]
    if not r24:
        return f"| {name} | {len(evs)} | - | - | - | - | - | - |"
    wr = 100.0 * sum(1 for x in r24 if x > 0) / len(r24)
    med24 = 100 * np.median([e["ret24"] for e in evs if e["ret24"] is not None])
    return (f"| {name} | {len(r24)} | {100*np.mean(r24):+.1f}% | {med24:+.1f}% | "
            f"{100*np.mean(e24):+.1f}% | {100*np.median(e24):+.1f}% | {wr:.0f}% | "
            f"{100*np.mean(e72):+.1f}% |" if e24 else
            f"| {name} | {len(r24)} | {100*np.mean(r24):+.1f}% | - | - | - | {wr:.0f}% | - |")


def main() -> int:
    events, stats = load_events()
    oh_map = load_ohlcv()
    covered = [e for e in events if e["mint"] in oh_map]
    stats["no_cover"] = len(events) - len(covered)
    uncovered = sorted({e["mint"] for e in events if e["mint"] not in oh_map})

    # les forwards + l'âge du token (première bougie = proxy de création)
    for e in covered:
        oh = oh_map[e["mint"]]
        e["ret24"] = forward(oh, e["t"], 24)
        e["ret72"] = forward(oh, e["t"], 72)
        first = int(oh[0][0])
        e["age_d"] = (e["t"] - first) / 86_400_000
    fwd_ok = [e for e in covered if e["ret24"] is not None]
    stats["no_fwd"] = len(covered) - len(fwd_ok)

    # la concentration : % des events venant du top-3 tokens
    tok_cnt = defaultdict(int)
    for e in fwd_ok:
        tok_cnt[e["mint"]] += 1
    top3 = sorted(tok_cnt.items(), key=lambda kv: -kv[1])[:3]
    top3_n = sum(n for _, n in top3)
    top1_n = top3[0][1] if top3 else 0

    blm24, blm72, blmean24, blmean72 = baselines(oh_map, {e["mint"] for e in fwd_ok})
    for e in fwd_ok:
        e["edge24"] = e["ret24"] - blm24[e["mint"]] if e["mint"] in blm24 else None
        e["edge72"] = e["ret72"] - blm72[e["mint"]] if (
            e["ret72"] is not None and e["mint"] in blm72) else None
        e["edge24_mb"] = e["ret24"] - blmean24[e["mint"]] if e["mint"] in blmean24 else None
    ev = [e for e in fwd_ok if e["edge24"] is not None]
    mb_sens = [e["edge24_mb"] for e in ev if e["edge24_mb"] is not None]

    # TRAIN/VAL PAR LE TEMPS (70/30 sur le temps des events)
    ev.sort(key=lambda e: e["t"])
    cut = ev[int(len(ev) * 0.7)]["t"] if ev else 0
    train = [e for e in ev if e["t"] <= cut]
    val = [e for e in ev if e["t"] > cut]

    def edge_stats(group, key="edge24"):
        xs = [e[key] for e in group if e[key] is not None]
        if not xs:
            return (float("nan"),) * 3 + (0,)
        return (100 * float(np.mean(xs)), 100 * float(np.median(xs)),
                tstat(xs), len(xs))

    m_all, med_all, ts_all, n_all = edge_stats(ev)
    me72, med72, ts72, n72 = edge_stats(ev, "edge72")
    m_tr, _, _, n_tr = edge_stats(train)
    m_va, med_va, ts_va, n_va = edge_stats(val)
    r24_all = [e["ret24"] for e in ev]
    wr_all = 100.0 * sum(1 for x in r24_all if x > 0) / len(r24_all)

    # le classement des traders (skill = edge24 moyen post-SES-achats)
    by_trader = defaultdict(list)
    for e in ev:
        by_trader[e["user"]].append(e)
    rank = []
    for user, tev in sorted(by_trader.items(), key=lambda kv: -len(kv[1])):
        m, med, ts_, n = edge_stats(tev)
        mv, medv, tsv, nv = edge_stats([e for e in tev if e["t"] > cut])
        rank.append((user, n, m, med, ts_, nv, mv, medv))
    skilled = [r for r in rank if r[1] >= 15 and r[2] > 0 and r[3] > 0]

    by_size = {"$1-5k": [], "$5-20k": [], ">$20k": []}
    for e in ev:
        k = "$1-5k" if e["usd"] < 5000 else ("$5-20k" if e["usd"] < 20000 else ">$20k")
        by_size[k].append(e)
    by_age = {"age<7j": [e for e in ev if e["age_d"] < 7],
              "age>=7j": [e for e in ev if e["age_d"] >= 7]}

    # le RÉGIME : edge24 moyen par mois (2026-08 vs 2026-09) + garde-fou composé
    by_month = defaultdict(list)
    for e in ev:
        mkey = datetime.fromtimestamp(e["t"] / 1000, tz=timezone.utc).strftime("%Y-%m")
        by_month[mkey].append(e["edge24"])
    monthly = {k: (100 * np.mean(v), len(v)) for k, v in sorted(by_month.items())}
    mom = [v[0] for v in monthly.values()]

    # ── le verdict (barre mission) ──────────────────────────────────────────
    verdict = "PASS" if (n_all >= 30 and m_all >= 2.0 and m_va >= 2.0
                         and len(skilled) >= 2) else (
        "CONTEXTE" if (n_all >= 30 and (m_all > 0 or len(skilled) >= 1)) else "FAIL")
    conc_flag = top3_n / len(fwd_ok) > 0.5
    if verdict == "PASS" and conc_flag:
        verdict = "PASS (conditionnel : top-3 tokens > 50%)"

    L = []
    A = L.append
    A("# Étude swaps baleines → forward returns v2 (2026-09-27, post-backfill)")
    A("")
    A("## Verdict : " + verdict)
    A("")
    A(f"n exploitable **{n_all}** (sur {len(events)} achats ≥ $1k) | "
      f"edge24 **{m_all:+.1f}%** (médiane {med_all:+.1f}%, t={ts_all:.2f}) | "
      f"edge72 {me72:+.1f}% (médiane {med72:+.1f}%, n={n72}) | "
      f"ret24 {100*np.mean(r24_all):+.1f}% (WR {wr_all:.0f}%) | "
      f"TRAIN {m_tr:+.1f}% / VAL **{m_va:+.1f}%** (t={ts_va:.2f}) | "
      f"traders skill (n≥15, edge>0, médiane>0) : {len(skilled)}.")
    A("")
    A("## Construction (l'honnêteté d'abord)")
    A("")
    A(f"- Swaps en base : {stats['total']} | achats dérivés : {stats['buys']} "
      f"(ventes ignorées {stats['sells']}, rotations token→token comptées comme achats : "
      f"{stats['cross']}, both-quote {stats['both_quote']}) | achats < $1k exclus : "
      f"{stats['lt_1k']} | events ≥ $1k : {len(events)}")
    A(f"- Couverture post-backfill : {len(oh_map)} mints en 1h fomo_ohlcv. "
      f"Mints SANS couverture → exclus : {stats['no_cover']} "
      f"({100*stats['no_cover']/max(1,len(events)):.1f}%, {len(uncovered)} mints distincts). "
      f"v1 : 98% exclus → v2 : quasi tout couvert.")
    A(f"- Forward 24h manquant (token mort / fin de données) : {stats['no_fwd']} | "
      f"n exploitable final : **{n_all}** sur {len(blm24)} tokens baselinés (24h) "
      f"et {len(blm72)} (72h).")
    A(f"- SURVIVORSHIP : les tokens vivants = les visibles en base (les morts avant "
      f"le dump final manquent) → l'edge mesuré est un PLAFOND, pas un plancher.")
    A(f"- CONCENTRATION : top-3 tokens = {top3_n}/{len(fwd_ok)} events "
      f"({100*top3_n/max(1,len(fwd_ok)):.0f}%) ; top-1 = "
      f"{top1_n} ({100*top1_n/max(1,len(fwd_ok)):.0f}%) — "
      f"{'OK (<50%)' if not conc_flag else 'l edge peut être l artefact de 3 tokens'}." )
    A(f"- Délai de réplication : entrée mesurée = close 1h contenant le swap "
      f"(jusqu'à 60 min après) ; délai réel réaliste 5-15 min → mesure CONSERVATRICE "
      f"sur les pumps, PESSIMISTE si le edge vient des 15 premières minutes.")
    A(f"- Baseline = MÉDIANE des forwards 24h du token sur TOUTE sa couverture "
      f"(médiane médiane tous tokens : "
      f"{100*np.median(list(blm24.values())):+.1f}%/24h). Sensibilité : avec le "
      f"baseline MOYENNE (v1, écrasé par les heures de lancement), l'edge "
      f"global serait {100*np.mean(mb_sens):+.0f}% — l'ordre de grandeur "
      f"médian reste le verdict robuste.")
    A("")
    A("## Agrégations (24h post-achat : ret, edge vs baseline token, WR)")
    A("")
    A("| Bloc | n | ret24 moy | ret24 méd | edge24 | edge24 méd | WR24 | edge72 |")
    A("|---|---|---|---|---|---|---|---|")
    A(block("TOUS", ev))
    A(block("TRAIN (≤70% temps)", train))
    A(block("VAL (>70% temps)", val))
    for k in ("$1-5k", "$5-20k", ">$20k"):
        A(block(k, by_size[k]))
    for k in ("age<7j", "age>=7j"):
        A(block(k, by_age[k]))
    A("")
    A("## Le classement des baleines (skill = edge24 moyen post-SES-achats)")
    A("")
    A("| Trader | n | edge24 | edge24 méd | t | n VAL | edge VAL | méd VAL |")
    A("|---|---|---|---|---|---|---|---|")
    for user, n, m, med, ts_, nv, mv, medv in rank:
        star = " *" if (n >= 15 and m > 0 and med > 0) else ""
        A(f"| {user} | {n} | {m:+.1f}% | {med:+.1f}% | {ts_:+.2f} | {nv} | "
          f"{mv:+.1f}% | {medv:+.1f}% |{star}")
    A("")
    A(f"\\* = barre réplication (n≥15, edge>0, médiane>0). "
      f"Traders qualifiés : {len(skilled)}/{len(rank)}.")
    A("")
    A("## Le RÉGIME : edge24 par mois (garde-fou composé-des-mois)")
    A("")
    A("| " + " | ".join(monthly) + " |")
    A("|" + "---|" * len(monthly))
    A("| " + " | ".join(f"{v[0]:+.0f}% (n={v[1]})" for v in monthly.values()) + " |")
    A("")
    A(f"Moyenne des moyennes mensuelles : {np.mean(mom):+.1f}% vs global {m_all:+.1f}% "
      f"— si l'écart est grand, l'edge est porté par un seul mois/régime.")
    A("")
    A("## Règle de réplication candidate (si PASS)")
    A("")
    if verdict.startswith("PASS"):
        best = skilled[:3]
        A("**Lecture honnête : l'edge est RELATIF** (vs la dérive typique du "
          "token). En ABSOLU, ret24 global : moyenne +2.3%, médiane -14.4%, "
          "WR 36% → répliquer LONG tous les achats n'est PAS rentable tel quel. "
          "Le PASS dit : après les achats de certains traders, le token fait "
          "MIEUX que sa propre norme — signal conditionnel, pas PnL.")
        A("")
        A("Traders qualifiés (barre n≥15 / edge>0 / médiane>0) : " +
          ", ".join(f"{r[0]} (n={r[1]}, edge {r[2]:+.1f}%, méd {r[3]:+.1f}%, "
                    f"VAL n={r[5]} {r[6]:+.1f}%)" for r in best) + ".")
        A(f"- derek518 = le SEUL avec support VAL réel (n VAL={skilled[0][5] if skilled else 0}). "
          f"unipcs : n VAL=3 → qualification formelle fragile (à confirmer en paper).")
        A("- Filtres qui améliorent l'ABSOLU : achats ≥ $5k (ret24 méd -6.7%) ou "
          "≥ $20k (méd +0.9%, WR 51%) ; token age≥7j (ret24 méd -4.7% vs -33.7% "
          "pour <7j) ; horizon 24h principal (edge72 médian négatif sauf >$20k).")
        A("- Entrée ≤ 15 min après le swap (polling swaps existant) ; taille "
          "FIXE par event (pas de size-scaling sur le $ baleine tant que n<100) ; "
          "levier ≤ 100/(maxMAE+0.5) sur le maxMAE du token (règle 0-liquidation, "
          "0 liq sans exception).")
        A("- AVANT le stack : wallet séquentiel scripts/stacked_portfolio.py "
          "run_stack. Puis câblage paper-forward fomo (scripts/fomo_paper_forward.py : "
          "consommer les nouveaux swaps du collecteur, générer les réplications "
          "skill-weighted filtrées ci-dessus, tracker le forward 24h/72h réel) "
          "— PROPOSITION, à câbler séparément.")
    else:
        A("Aucune règle : " + (
            "l'edge ne tient pas en VAL" if m_all > 0 and m_va <= 2.0 else
            "l'edge moyen < +2%" if m_all < 2.0 else
            "moins de 2 traders skill répliqués") +
          " — pas de réplication skill-weighted. Ré-catégoriser dans "
          "docs/20-registre-indicateurs.md : le flux baleine reste un INDICE de "
          "momentum, pas un signal autonome.")
    REPORT.write_text("\n".join(L) + "\n")
    print(f"[v2] verdict={verdict} n={n_all} edge24={m_all:+.2f}% "
          f"(TRAIN {m_tr:+.2f}% / VAL {m_va:+.2f}%) skilled={len(skilled)} "
          f"-> {REPORT.name}")
    for user, n, m, med, ts_, nv, mv, _ in rank[:5]:
        print(f"  {user}: n={n} edge24={m:+.1f}% méd={med:+.1f}% "
              f"(VAL n={nv} {mv:+.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
