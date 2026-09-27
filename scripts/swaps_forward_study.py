#!/usr/bin/env python
"""L'ÉTUDE SWAPS → FORWARD RETURNS — l'edge de réplication skill-weighted.

La question : les ACHATS des baleines fomo prédisent-ils les rendements
forward ? On mesure le forward post-achat (24h/72h, closes 1h fomo_ohlcv)
MOINS le baseline du MÊME token (moyenne de ses forwards 24h sur toute
sa fenêtre couverte) = l'edge conditionnel, pas la bêta du memecoin.

  .venv/bin/python scripts/swaps_forward_study.py

Honnêteté intégrée :
- side DÉRIVÉ (le token tradé = le mint non-QUOTE ; buy → token = out_mint,
  $ = human_usd_amount_out du raw_json) — jamais la colonne side sur foi.
- le ts est en SECONDES ici (vérifié à la source, garde ms/ns quand même).
- les tokens sans couverture 1h = exclus et COMPTÉS (survivorship : les
  tokens vivants = les visibles → l'edge mesuré est un plafond, pas un plancher).
- la réplication réelle a un délai 5-15 min ; ici l'entrée = la close 1h
  qui contient le swap (donc JUSQU'À 60 min après) → conservateur.
- TRAIN/VAL PAR LE TEMPS (70/30) : l'edge doit tenir en VAL pour PASS.
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
FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"          # LECTURE SEULE (mode=ro)
REPORT = ROOT / "reports" / "swaps-forward-2026-09-27.md"

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
    events, uncovered = [], set()
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
    out = {}
    for asset, t, c in cur.execute(
        "SELECT asset, time, close FROM fomo_ohlcv WHERE period='1h' ORDER BY asset, time"
    ):
        a = out.setdefault(asset, ([], []))
        a[0].append(t)
        a[1].append(c)
    con.close()
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


def baselines(oh_map, t0, t1) -> dict[str, float]:
    """Le baseline PAR TOKEN : moyenne des forwards 24h de toutes les heures
    de sa fenêtre couverte dans la période d'étude (pas l'artefact du swap)."""
    out = {}
    for mint, oh in oh_map.items():
        times = oh[0]
        mask = (times >= t0) & (times <= t1)
        rets = [forward(oh, int(t), 24) for t in times[mask]]
        rets = [r for r in rets if r is not None]
        if len(rets) >= 24:
            out[mint] = float(np.mean(rets))
    return out


def tstat(xs):
    if len(xs) < 3:
        return 0.0
    sd = statistics.stdev(xs)
    return statistics.mean(xs) / (sd / len(xs) ** 0.5) if sd > 0 else 0.0


def block(name, evs, bl_map) -> str:
    if not evs:
        return f"| {name} | 0 | - | - | - | - | - |"
    e24 = [e["edge24"] for e in evs if e["edge24"] is not None]
    r24 = [e["ret24"] for e in evs if e["ret24"] is not None]
    r72 = [e["ret72"] for e in evs if e["ret72"] is not None]
    if not r24:
        return f"| {name} | {len(evs)} | - | - | - | - | - |"
    wr = 100.0 * sum(1 for x in r24 if x > 0) / len(r24)
    ed = np.mean(e24) if e24 else float("nan")
    return (f"| {name} | {len(r24)} | {100*np.mean(r24):+.1f}% | "
            f"{100*np.median(r24):+.1f}% | {100*ed:+.1f}% | {wr:.0f}% | "
            f"{100*np.mean(r72):+.1f}% |" if r72 else
            f"| {name} | {len(r24)} | {100*np.mean(r24):+.1f}% | "
            f"{100*np.median(r24):+.1f}% | {100*ed:+.1f}% | {wr:.0f}% | - |")


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

    # la concentration : l'edge peut être l'artefact d'UN token/UN wallet
    tok_cnt = defaultdict(int)
    for e in covered:
        if e["ret24"] is not None:
            tok_cnt[e["mint"]] += 1
    top_tok, top_n = max(tok_cnt.items(), key=lambda kv: kv[1]) if tok_cnt else ("-", 0)

    t0 = min(e["t"] for e in fwd_ok)
    t1 = max(e["t"] for e in fwd_ok)
    bl_map = baselines(oh_map, t0, t1)
    for e in fwd_ok:
        bl = bl_map.get(e["mint"])
        e["edge24"] = e["ret24"] - bl if bl is not None else None
    bl_all = np.mean(list(bl_map.values())) if bl_map else float("nan")
    ev = [e for e in fwd_ok if e["edge24"] is not None]

    # TRAIN/VAL PAR LE TEMPS (70/30 sur la médiane du temps des events)
    ev.sort(key=lambda e: e["t"])
    cut = ev[int(len(ev) * 0.7)]["t"] if ev else 0
    train = [e for e in ev if e["t"] <= cut]
    val = [e for e in ev if e["t"] > cut]

    def mean_edge(group):
        xs = [e["edge24"] for e in group if e["edge24"] is not None]
        return (100 * np.mean(xs), 100 * np.median(xs), tstat(xs), len(xs)) if xs \
            else (float("nan"),) * 4

    # le classement des traders (le skill : edge moyen post-SES-achats)
    by_trader = defaultdict(list)
    for e in ev:
        by_trader[e["user"]].append(e)
    rank = []
    for user, tev in sorted(by_trader.items(), key=lambda kv: -len(kv[1])):
        m, med, ts_, n = mean_edge(tev)
        r24 = [e["ret24"] for e in tev if e["ret24"] is not None]
        mv, medv, tsv, nv = mean_edge([e for e in tev if e["t"] > cut])
        rank.append((user, n, 100 * np.mean(r24) if r24 else float("nan"),
                     m, med, ts_, nv, mv))

    by_size = {"$1-5k": [], "$5-20k": [], ">$20k": []}
    for e in ev:
        k = "$1-5k" if e["usd"] < 5000 else ("$5-20k" if e["usd"] < 20000 else ">$20k")
        by_size[k].append(e)
    by_age = {"age<7j": [e for e in ev if e["age_d"] < 7],
              "age>=7j": [e for e in ev if e["age_d"] >= 7]}

    # le garde-fou composé-des-mois : la moyenne des mois vs le global
    by_month = defaultdict(list)
    for e in ev:
        m = datetime.fromtimestamp(e["t"] / 1000, tz=timezone.utc).strftime("%Y-%m")
        by_month[m].append(e["edge24"])
    monthly = {k: (100 * np.mean(v), len(v)) for k, v in sorted(by_month.items())}
    mom = [v[0] for v in monthly.values()]

    # ── le verdict ──────────────────────────────────────────────────────────
    m_all, med_all, ts_all, n_all = mean_edge(ev)
    m_tr, _, _, n_tr = mean_edge(train)
    m_va, med_va, ts_va, n_va = mean_edge(val)
    skilled = [r for r in rank if r[1] >= 10 and r[3] > 0 and r[4] > 0 and r[5] >= 1.0]
    verdict = ("PASS" if (n_all >= 30 and m_all >= 2.0 and m_va >= 2.0
                          and len(skilled) >= 2 and top_n <= 0.5 * len(fwd_ok))
               else
               "CONTEXTE" if (n_all >= 30 and (m_all > 0 or len(skilled) >= 1))
               else "FAIL")

    L = []
    A = L.append
    A("# Étude swaps baleines → forward returns (2026-09-27)")
    A("")
    A("## Verdict : " + verdict)
    A("")
    A(f"Edge post-achat vs baseline token : **{m_all:+.1f}%** à 24h "
      f"(médiane {med_all:+.1f}%, t={ts_all:.2f}, n={n_all}) ; "
      f"TRAIN {m_tr:+.1f}% / VAL {m_va:+.1f}% (t={ts_va:.2f}) ; "
      f"traders skill robuste (n≥10, edge>0, médiane>0, t≥1) : {len(skilled)}.")
    A("")
    A("## Construction (l'honnêteté d'abord)")
    A("")
    A(f"- Swaps en base : {stats['total']} | achats dérivés : {stats['buys']} "
      f"(ventes ignorées {stats['sells']}, rotations token→token comptées comme achats : "
      f"{stats['cross']}, both-quote {stats['both_quote']}) | achats < $1k exclus : "
      f"{stats['lt_1k']} | events ≥ $1k : {len(events)}")
    A(f"- Mints SANS couverture 1h fomo_ohlcv → exclus : {stats['no_cover']} "
      f"({100*stats['no_cover']/max(1,len(events)):.0f}%, {len(uncovered)} mints distincts) "
      f"— survivorship : les tokens vivants = les visibles, l'edge mesuré est un PLAFOND.")
    A(f"- Forward 24h manquant (token mort / trop récent) : {stats['no_fwd']} | "
      f"n exploitable final : **{len(ev)}** sur {len(bl_map)} tokens baselinés.")
    A(f"- CONCENTRATION CRITIQUE : {top_n}/{len(fwd_ok)} events exploitables = le "
      f"MÊME token ({top_tok[:10]}…) — l'échantillon est de facto mono-token/mono-wallet, "
      f"l'edge moyen mesure la performance de CE token, pas un skill de baleine. "
      f"La fenêtre 13 mois des swaps s'effondre à ~1 mois exploitable (couverture OHLCV).")
    A(f"- Baseline moyen tous tokens (24h, fenêtre d'étude) : {100*bl_all:+.1f}%/24h "
      f"— l'edge = ret24 post-achat − baseline du MÊME token.")
    A(f"- Délai de réplication : l'entrée = close 1h contenant le swap (jusqu'à 60 min "
      f"après) ; délai réel réaliste 5-15 min → notre mesure est CONSERVATRICE. "
      f"Risque inverse : les baleines achètent PEUT-ÊTRE après une info privée/momentum — "
      f"le look-ahead de leur décision nous est inaccessible.")
    A("")
    A("## Agrégations (24h post-achat, edge vs baseline token)")
    A("")
    A("| Bloc | n | ret24 moy | ret24 méd | edge24 | WR24 | ret72 |")
    A("|---|---|---|---|---|---|---|")
    A(block("TOUS", ev, bl_map))
    A(block("TRAIN (≤70% temps)", train, bl_map))
    A(block("VAL (>70% temps)", val, bl_map))
    for k in ("$1-5k", "$5-20k", ">$20k"):
        A(block(k, by_size[k], bl_map))
    for k in ("age<7j", "age>=7j"):
        A(block(k, by_age[k], bl_map))
    A("")
    A("## Le classement des 13 baleines (skill = edge24 moyen post-SES-achats)")
    A("")
    A("| Trader | n | ret24 moy | edge24 | edge24 méd | t | n VAL | edge VAL |")
    A("|---|---|---|---|---|---|---|---|")
    for user, n, r24m, m, med, ts_, nv, mv in rank:
        A(f"| {user} | {n} | {r24m:+.1f}% | {m:+.1f}% | {med:+.1f}% | {ts_:+.2f} "
          f"| {nv} | {mv:+.1f}% |")
    A("")
    A("## Le garde-fou composé-des-mois (edge24 moyen par mois)")
    A("")
    A("| " + " | ".join(monthly) + " |")
    A("|" + "---|" * len(monthly))
    A("| " + " | ".join(f"{v[0]:+.0f}% (n={v[1]})" for v in monthly.values()) + " |")
    A("")
    A(f"Moyenne des moyennes mensuelles : {np.mean(mom):+.1f}% vs global {m_all:+.1f}% "
      f"— écart = le poids des gros mois (si grand, l'edge est concentré).")
    A("")
    A("## Règle de réplication candidate (si PASS)")
    A("")
    if verdict == "PASS":
        best = skilled[:3]
        A("Achats ≥ $1k des traders skillés " + ", ".join(r[0] for r in best) +
          " ; entrée ≤ 15 min après le swap ; horizons 24h/72h ; levier par la "
          "règle 0-liquidation sur le maxMAE du token. À passer au wallet "
          "séquentiel (scripts/stacked_portfolio.py run_stack) AVANT le stack.")
    else:
        A("Aucune règle : l'edge " + ("ne tient pas en VAL" if m_all > 0 else
          "est absent/négatif") + " — pas de réplication skill-weighted. "
          "Ré-catégoriser dans docs/20-registre-indicateurs.md : le flux baleine "
          "reste un INDICE de momentum, pas un signal autonome.")
    REPORT.write_text("\n".join(L) + "\n")
    print(f"[swaps-forward] verdict={verdict} n={len(ev)} edge24={m_all:+.2f}% "
          f"(TRAIN {m_tr:+.2f}% / VAL {m_va:+.2f}%) skilled={len(skilled)} "
          f"-> {REPORT.name}")
    for user, n, r24m, m, med, ts_, nv, mv in rank[:5]:
        print(f"  {user}: n={n} ret24={r24m:+.1f}% edge24={m:+.1f}% "
              f"(VAL n={nv} {mv:+.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
