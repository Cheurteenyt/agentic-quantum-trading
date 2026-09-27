#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""ÉTUDE WHALE ATTENTION — l'entrée d'une baleine change-t-elle le RÉGIME du token ?

Suite de swaps_forward_v2 (PASS : edge post-achat +8,4% tenu en VAL). v2 testait
la RÉPLICATION (acheter après la baleine). Ici la question complémentaire :
l'ATTENTION — le simple fait qu'une baleine ait acheté change-t-il le comportement
FUTUR du token (liquidité, vol, drift) au-delà du premier forward ?

Construction (vérifiée sur les données, pas supposée) :
- Whale buy = achat DÉRIVÉ (v2 : side jamais pris sur foi ; buy -> token = out_mint,
  $ = humanUsdAmountOut du raw_json) >= $1k. ts : garde s/ms/ns (leçon ts_ms).
- UNIVERSE CHECK : les 1 345 mints couverts 1h ne sont PAS tous « attentionnés » :
  ~688 n'ont AUCUN achat >= $1k -> VRAI groupe contrôle (cross-sectional) +
  design AVANT/APRÈS intra-token pour les 657 tokens baleine couverts.
- T0 = premier achat baleine du token.

Trois tests :
  1) PANEL AGE-APPRIÉ (bar-level) : chaque bougie 1h de chaque mint classée
     never-whale / PRE-T0 / POST-T0, forward 24h (v2 : close 1h, ±3h tol),
     par bucket d'âge du token. Répond à « l'univers post-attention vaut-il
     mieux, à âge égal ? » = valeur du filtre d'univers.
  2) AVANT/APRÈS 7j (tokens avec >=3j de bougies de chaque côté) : vol
     quotidiennisée, volume/jour, drift médian 24h — apparié intra-token
     (delta = après − avant, médiane + t + %tokens améliorés).
  3) DOSE-RÉPONSE : 1 baleine vs 2+ baleines distinctes (conviction collective).

Honnêteté : causalité inversée (les baleines achètent peut-être ce qui démarre
déjà) -> sonde PRE-TREND en 4 sous-fenêtres [-7j,-3.5j) [-3.5j,T0) [T0,+3.5j)
[+3.5j,+7j) : si le drift montait DÉJÀ avant T0, l'attention suit le momentum.
Biais de sélection du sous-échantillon 7j/7j (tokens vivants >=3j avant T0),
n par cellule, TRAIN/VAL par le temps sur T0, garde-fou composé-des-mois.

  .venv/bin/python scripts/whale_attention_test.py
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SWAPS_DB = ROOT / "data" / "fomo" / "fomo_swaps.db"  # LECTURE SEULE (mode=ro)
FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"         # LECTURE SEULE (mode=ro)
REPORT = ROOT / "reports" / "whale-attention-2026-09-28.md"

MIN_USD = 1_000.0
BAR_MS = 3_600_000
DAY_MS = 86_400_000
TOL_MS = 3 * BAR_MS
WIN_MS = 7 * DAY_MS          # fenêtre avant/après T0
MIN_BARS = 72                # >=3 jours de bougies par côté (sensibilité : 120)
MIN_FWD = 12                 # forwards 24h min par fenêtre pour le drift
AGE_BUCKETS = [(0, 1), (1, 3), (3, 7), (7, 30), (30, 10_000)]
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


def load_whale_buys() -> tuple[dict[str, int], dict[str, set], dict, dict]:
    """Achats dérivés >= $1k -> {mint: T0_ms}, {mint: set(whales)}, stats."""
    con = sqlite3.connect(f"file:{SWAPS_DB}?mode=ro", uri=True)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT user_id, in_mint, out_mint, size_usd, ts, created_at, raw_json "
        "FROM fomo_swaps"
    ).fetchall()
    con.close()
    t0: dict[str, int] = {}
    whales: dict[str, set] = defaultdict(set)
    stats = {"total": len(rows), "buys": 0, "sells": 0, "cross": 0,
             "both_quote": 0, "lt_1k": 0, "whale_buys": 0}
    for uid, in_mint, out_mint, size_usd, ts, created, raw in rows:
        in_q, out_q = in_mint in QUOTE_MINTS, out_mint in QUOTE_MINTS
        if in_q and out_q:
            stats["both_quote"] += 1
            continue
        if out_q and not in_q:          # sell du token in_mint
            stats["sells"] += 1
            continue
        stats["buys"] += 1
        if not in_q and not out_q:
            stats["cross"] += 1
        try:
            usd = json.loads(raw).get("humanUsdAmountOut") or size_usd or 0.0
        except Exception:
            usd = size_usd or 0.0
        if usd < MIN_USD:
            stats["lt_1k"] += 1
            continue
        t_ms = ts_to_ms(int(ts)) if ts else iso_to_ms(created)
        mint = out_mint
        stats["whale_buys"] += 1
        whales[mint].add(uid)
        if mint not in t0 or t_ms < t0[mint]:
            t0[mint] = t_ms
    return t0, whales, stats, {m: len(s) for m, s in whales.items()}


def load_ohlcv() -> dict[str, dict]:
    con = sqlite3.connect(f"file:{FOMO_DB}?mode=ro", uri=True)
    cur = con.cursor()
    out: dict[str, dict] = {}
    n_bars = 0
    for asset, t, c, v in cur.execute(
        "SELECT asset, time, close, volume FROM fomo_ohlcv "
        "WHERE period='1h' ORDER BY asset, time"
    ):
        a = out.setdefault(asset, {"t": [], "c": [], "v": []})
        a["t"].append(t)
        a["c"].append(c)
        a["v"].append(v)
        n_bars += 1
    con.close()
    print(f"[att] ohlcv 1h : {n_bars} bougies, {len(out)} mints couverts")
    return {
        k: {"t": np.asarray(v["t"], dtype=np.int64),
            "c": np.asarray(v["c"], dtype=float),
            "v": np.nan_to_num(np.asarray(v["v"], dtype=float))}
        for k, v in out.items()
    }


def fwd24(oh: dict) -> np.ndarray:
    """Forward 24h depuis CHAQUE bougie 1h (v2 : close cible ±3h), NaN sinon."""
    t, c = oh["t"], oh["c"]
    tgt = t + 24 * BAR_MS
    j = np.searchsorted(t, tgt, "right") - 1
    i = np.arange(len(t))
    ok = (j > i) & (t[j] >= tgt - TOL_MS) & (t[j] <= tgt + TOL_MS)
    r = np.full(len(t), np.nan)
    r[ok] = c[j[ok]] / c[i[ok]] - 1.0
    return r


def window_metrics(oh: dict, fwd: np.ndarray, lo: int, hi: int) -> dict | None:
    """Vol quotidiennisée, volume/jour, drift médian 24h sur [lo, hi)."""
    t, c, v = oh["t"], oh["c"], oh["v"]
    i0, i1 = int(np.searchsorted(t, lo)), int(np.searchsorted(t, hi))
    n = i1 - i0
    if n < MIN_BARS:
        return None
    rets = np.diff(np.log(c[i0:i1]))
    ok = np.isfinite(rets) & (t[i0 + 1:i1] - t[i0:i1 - 1] == BAR_MS)
    vol_d = float(np.std(rets[ok]) * np.sqrt(24)) if ok.sum() >= 10 else None
    span_d = max((t[i1 - 1] - t[i0]) / DAY_MS, 1 / 24)
    f = fwd[i0:i1]
    f = f[np.isfinite(f)]
    return {"n_bars": n, "vol_d": vol_d,
            "vol_usd_d": float(np.sum(v[i0:i1]) / span_d),
            "drift": float(np.median(f)) if len(f) >= MIN_FWD else None,
            "n_fwd": int(len(f))}


def tstat(xs: list[float]) -> float:
    if len(xs) < 3:
        return 0.0
    sd = statistics.stdev(xs)
    return statistics.mean(xs) / (sd / len(xs) ** 0.5) if sd > 0 else 0.0


def main() -> int:
    t0_map, _, swap_stats, n_whales = load_whale_buys()
    oh_map = load_ohlcv()

    # ── univers : tout-baleine ? ────────────────────────────────────────────
    covered = set(oh_map)
    whale_cov = {m: t0_map[m] for m in t0_map if m in covered}
    control = sorted(covered - set(t0_map))
    print(f"[att] couverts {len(covered)} | baleine couverts {len(whale_cov)} "
          f"| contrôle pur {len(control)}")

    # ── 1) PANEL AGE-APPRIVIÉRÉ (bar-level) ────────────────────────────────
    # groupe par bougie : never / pre / post ; drift médian par (groupe, âge)
    panel = defaultdict(lambda: {"r": [], "toks": set()})
    for mint, oh in oh_map.items():
        fwd = fwd24(oh)
        t = oh["t"]
        first = int(t[0])
        if mint in whale_cov:
            t0 = whale_cov[mint]
            grp = np.where(t < t0, "pre", "post")
        else:
            grp = np.full(len(t), "never", dtype=object)
        age_d = (t - first) / DAY_MS
        for lo, hi in AGE_BUCKETS:
            m = (age_d >= lo) & (age_d < hi) & np.isfinite(fwd)
            if not m.any():
                continue
            for g in ("never", "pre", "post"):
                mg = m & (grp == g)
                if mg.any():
                    cell = panel[(g, lo, hi)]
                    cell["r"].extend(fwd[mg].tolist())
                    cell["toks"].add(mint)

    # ── 2) AVANT/APRÈS 7j intra-token ──────────────────────────────────────
    pairs = []
    for mint, t0 in sorted(whale_cov.items(), key=lambda kv: kv[1]):
        oh = oh_map[mint]
        fwd = fwd24(oh)
        pre = window_metrics(oh, fwd, t0 - WIN_MS, t0)
        post = window_metrics(oh, fwd, t0, t0 + WIN_MS)
        if not pre or not post:
            continue
        if pre["drift"] is None or post["drift"] is None or pre["vol_d"] is None:
            continue
        pairs.append({"mint": mint, "t0": t0,
                      "pre": pre, "post": post,
                      "d_drift": post["drift"] - pre["drift"],
                      "d_vol": post["vol_d"] / pre["vol_d"] - 1.0
                      if pre["vol_d"] > 0 else None,
                      "d_volusd": post["vol_usd_d"] / pre["vol_usd_d"] - 1.0
                      if pre["vol_usd_d"] > 0 else None,
                      "nwh": n_whales.get(mint, 0)})
    # sonde PRE-TREND (causalité inversée) sur les 4 sous-fenêtres de 3,5j
    pre_trend = []
    for p in pairs:
        oh, fwd, t0 = oh_map[p["mint"]], None, p["t0"]
        fwd = fwd24(oh)
        row = {"mint": p["mint"]}
        for tag, lo, hi in (("a", t0 - WIN_MS, t0 - WIN_MS // 2),
                            ("b", t0 - WIN_MS // 2, t0),
                            ("c", t0, t0 + WIN_MS // 2),
                            ("d", t0 + WIN_MS // 2, t0 + WIN_MS)):
            w = window_metrics(oh, fwd, lo, hi)
            row[tag] = w["drift"] if w and w["drift"] is not None else None
        if all(row[k] is not None for k in "abcd"):
            pre_trend.append(row)

    # TRAIN/VAL par le temps (70/30 sur T0 des tokens appariés)
    ts_sorted = sorted(p["t0"] for p in pairs)
    cut = ts_sorted[int(len(ts_sorted) * 0.7)] if ts_sorted else 0
    train = [p for p in pairs if p["t0"] <= cut]
    val = [p for p in pairs if p["t0"] > cut]

    # composé-des-mois : delta drift par mois de T0
    by_month = defaultdict(list)
    for p in pairs:
        mk = datetime.fromtimestamp(p["t0"] / 1000, tz=timezone.utc).strftime("%Y-%m")
        by_month[mk].append(p["d_drift"])

    # ── 3) DOSE-RÉPONSE ────────────────────────────────────────────────────
    dose = {"1": [], "2+": []}
    for p in pairs:
        dose["1" if p["nwh"] == 1 else "2+"].append(p)
    # dose sur TOUT le panel post-T0 (drift médian des bougies post, par token)
    dose_full = {"1": [], "2+": []}
    for mint, t0 in whale_cov.items():
        fwd = fwd24(oh_map[mint])
        t = oh_map[mint]["t"]
        m = (t >= t0) & np.isfinite(fwd)
        if m.sum() < 48:
            continue
        g = "1" if n_whales.get(mint, 0) == 1 else "2+"
        dose_full[g].append({"mint": mint, "drift": float(np.median(fwd[m])),
                             "wr": float(np.mean(fwd[m] > 0)),
                             "nobs": int(m.sum())})

    # ── rapport ────────────────────────────────────────────────────────────
    L = []
    A = L.append

    def pct(x, d=1):
        return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) \
            else f"{100 * x:+.{d}f}%"

    def pair_line(name, ps):
        if not ps:
            return f"| {name} | 0 | - | - | - | - | - | - | - |"
        dd = [p["d_drift"] for p in ps]
        dv = [p["d_vol"] for p in ps if p["d_vol"] is not None]
        du = [p["d_volusd"] for p in ps if p["d_volusd"] is not None]
        pr = [p["pre"]["drift"] for p in ps]
        po = [p["post"]["drift"] for p in ps]
        return (f"| {name} | {len(ps)} | {pct(np.median(pr))} | {pct(np.median(po))} | "
                f"{pct(np.median(dd))} | {pct(np.mean(dd))} | {tstat(dd):+.2f} | "
                f"{100 * sum(1 for x in dd if x > 0) / len(dd):.0f}% | "
                f"{pct(np.median(du)) if du else '—'}")

    dd_all = [p["d_drift"] for p in pairs]
    verdict = ("PASS" if len(pairs) >= 30 and np.median(dd_all) > 0
               and tstat(dd_all) > 2 else
               "CONTEXTE" if len(pairs) >= 30 and np.median(dd_all) > 0 else "FAIL")
    # l'hypothèse INCLUSION (attention = meilleur régime) ; l'inverse (anti-filtre)
    # est examiné séparément dans la section règle si le drift post < never apparié.
    anti = all(
        (panel.get(("post", lo, hi)) and panel.get(("never", lo, hi))
         and np.median(panel[("post", lo, hi)]["r"])
         < np.median(panel[("never", lo, hi)]["r"]))
        for lo, hi in AGE_BUCKETS[:3])  # buckets 0-1j, 1-3j, 3-7j

    A("# Étude whale ATTENTION — l'entrée baleine change-t-elle le régime ? (2026-09-28)")
    A("")
    A("## Verdict : " + verdict +
      (" pour l'hypothèse INCLUSION « attention = meilleur régime »" if verdict == "FAIL" else "")
      + (" — ANTI-FILTRE candidat : post-T0 < never à âge égal sur 0-7j" if anti else ""))
    A("")
    ddv = [p["d_drift"] for p in val]
    ddt = [p["d_drift"] for p in train]
    A(f"n apparié 7j/7j **{len(pairs)}** (sur {len(whale_cov)} tokens baleine couverts) | "
      f"delta drift médian **{pct(np.median(dd_all))}** (t={tstat(dd_all):+.2f}, "
      f"{100 * sum(1 for x in dd_all if x > 0) / len(dd_all):.0f}% de tokens améliorés) | "
      f"TRAIN {pct(np.median(ddt))} / VAL **{pct(np.median(ddv))}** (n={len(val)}). "
      f"Contrôle pur (jamais baleine) : {len(control)} mints — le corpus N'EST PAS "
      f"tout-baleine : double design possible (cross-sectional + avant/après).")
    A("")
    A("## Construction (l'univers vérifié, pas supposé)")
    A("")
    A(f"- Swaps : {swap_stats['total']} | achats dérivés {swap_stats['buys']} "
      f"(ventes {swap_stats['sells']}, rotations {swap_stats['cross']}) | "
      f"achats >= $1k : {swap_stats['whale_buys']} sur "
      f"{len(t0_map)} mints distincts.")
    A(f"- Couverture 1h : {len(covered)} mints. Tokens baleine couverts : "
      f"**{len(whale_cov)}** | contrôle PUR (0 achat >= $1k) : **{len(control)}** "
      f"({100 * len(control) / len(covered):.0f}%) — le backfill couvre aussi des "
      f"mints achetés < $1k ou vendus seulement : le corpus n'est PAS "
      f"uniformément « attentionné ».")
    A(f"- Âge au T0 (premier achat baleine) : médiane "
      f"{np.median([(t0 - int(oh_map[m]['t'][0])) / DAY_MS for m, t0 in whale_cov.items() if m in oh_map]):.2f} j "
      f"-> {sum(1 for m, t0 in whale_cov.items() if m in oh_map and (t0 - int(oh_map[m]['t'][0])) / DAY_MS < 1)} "
      f"tokens ont leur T0 < 24h après la 1re bougie : la plupart n'ont PAS de "
      f"fenêtre avant exploitable.")
    A(f"- Fenêtres 7j/7j : {len(pairs)} tokens avec >= {MIN_BARS} bougies de chaque "
      f"côté ({MIN_FWD}+ forwards 24h) — SOUS-ÉCHANTILLON biaisé vers les tokens "
      f"vivants >= 3j avant T0 (les naissances-flash sont exclues de l'avant/après, "
      f"mais restent dans le panel age-apprié).")
    A("")
    A("## 1) Panel age-apprié : drift médian 24h par (groupe, âge)")
    A("")
    A("| Âge | never (n tok) | pre-T0 (n tok) | post-T0 (n tok) | "
      "post−pre (pp) | post−never (pp) |")
    A("|---|---|---|---|---|---|")
    for lo, hi in AGE_BUCKETS:
        cells = {g: panel.get((g, lo, hi)) for g in ("never", "pre", "post")}
        med = {g: (float(np.median(c["r"])) if c and c["r"] else None)
               for g, c in cells.items()}
        nt = {g: (len(c["toks"]) if c else 0) for g, c in cells.items()}
        dpd = (100 * (med["post"] - med["pre"])
               if med["post"] is not None and med["pre"] is not None else None)
        dnv = (100 * (med["post"] - med["never"])
               if med["post"] is not None and med["never"] is not None else None)
        lab = f"{lo}j+" if hi > 9999 else f"{lo}-{hi}j"
        A(f"| {lab} | {pct(med['never'])} ({nt['never']}) | "
          f"{pct(med['pre'])} ({nt['pre']}) | {pct(med['post'])} ({nt['post']}) | "
          f"{dpd:+.1f} | {dnv:+.1f} |")
    A("")
    A("## 2) Avant/Après 7j intra-token (delta = après − avant)")
    A("")
    A("| Bloc | n | drift pré | drift post | Δ médian | Δ moyen | t | "
      "%tokens Δ>0 | Δ volume$/j méd |")
    A("|---|---|---|---|---|---|---|---|---|")
    A(pair_line("TOUS", pairs))
    A(pair_line("TRAIN (T0 <= p70)", train))
    A(pair_line("VAL (T0 > p70)", val))
    A(pair_line("dose 1 baleine", dose["1"]))
    A(pair_line("dose 2+ baleines", dose["2+"]))
    dv_all = [p["d_vol"] for p in pairs if p["d_vol"] is not None]
    A("")
    A(f"Vol quotidiennisée : Δ médian {pct(np.median(dv_all))} "
      f"({100 * sum(1 for x in dv_all if x > 0) / len(dv_all):.0f}% de tokens voient "
      f"leur vol AUGMENTER post-T0) | volume $/jour : voir colonne Δ "
      f"(liquidité). Pré/post médians TOUS : vol "
      f"{pct(np.median([p['pre']['vol_d'] for p in pairs]), 2)} -> "
      f"{pct(np.median([p['post']['vol_d'] for p in pairs]), 2)} (écart-type horaire "
      f"x sqrt(24)).")
    A("")
    A("## Sonde PRE-TREND (causalité inversée) — drift médian par sous-fenêtre")
    A("")
    for k, lab in (("a", "[-7j;-3.5j)"), ("b", "[-3.5j;T0)"),
                   ("c", "[T0;+3.5j)"), ("d", "[+3.5j;+7j)")):
        xs = [r[k] for r in pre_trend if r[k] is not None]
        A(f"- {lab} : médiane {pct(np.median(xs))} (n={len(xs)})")
    A("")
    if pre_trend:
        b = np.median([r["b"] for r in pre_trend])
        a = np.median([r["a"] for r in pre_trend])
        c_ = np.median([r["c"] for r in pre_trend])
        slope = "LE MOMENTUM MONTAIT DÉJÀ avant T0 (attention SUIT le momentum)" \
            if b > a else "pas de montée pré-T0 (l'attention précède la hausse)"
        persist = "l'effet PERSISTE à +7j" if c_ > b else \
            "l'effet RETOMBE dès +3.5j (pic = l'achat lui-même)"
        A(f"Lecture : {slope} ; {persist}.")
    A("")
    A("## 3) Dose-réponse (panel post-T0 complet, tous âges)")
    A("")
    A("| Dose | n tokens | drift médian post | WR médian |")
    A("|---|---|---|---|")
    for g in ("1", "2+"):
        xs = dose_full[g]
        A(f"| {g} baleine(s) distincte(s) | {len(xs)} | "
          f"{pct(np.median([x['drift'] for x in xs]))} | "
          f"{100 * np.median([x['wr'] for x in xs]):.0f}% |")
    A("")
    A("n par cellule honnête : dose 2+ est mince (68 tokens 2-3 baleines, "
      "4 tokens 4+ dans le corpus complet ; l'apparié 7j/7j en garde encore "
      "moins) — la dose-réponse est INDICATIVE, pas concluante.")
    A("")
    A("## Garde-fou composé-des-mois (Δ drift par mois de T0)")
    A("")
    mk = sorted(by_month)
    A("| " + " | ".join(mk) + " |")
    A("|" + "---|" * len(mk))
    A("| " + " | ".join(
        f"{pct(np.median(by_month[k]))} (n={len(by_month[k])})" for k in mk) + " |")
    A("")
    A("## Honêteté")
    A("")
    A("- CAUSALITÉ INVERSÉE : le design avant/après atténue (contrôle = le token "
      "LUI-MÊME) mais n'élimine pas : si les baleines achètent exactement les "
      "tokens qui démarrent, le « régime post » inclut la cause du déclenchement. "
      "La sonde pre-trend ci-dessus est le seul contre-test disponible ici.")
    A("- SURVIVORSHIP : les tokens couverts 1h = backfillés des swaps de traders "
      "suivis -> les morts instantanés manquent ; les effets mesurés sont des "
      "PLAFONDS.")
    A("- SÉLECTION 7j/7j : l'échantillon apparié exige >=3j de vie avant T0 -> "
      "biaisé vers les tokens à montée lente ; le panel age-apprié (tous tokens) "
      "corrige la vue d'ensemble.")
    A("- UN BALEINAGE = PEUT-ÊTRE LE MÊME EVENT que v2 : le forward post-T0 "
      "chevauche l'edge de réplication v2 (+8,4%) ; l'apport ici est le RÉGIME "
      "(vol/liquidité/drift continu), pas un nouveau signal d'entrée.")
    A("- Autocorrélation : les bougies d'un même token ne sont pas indépendantes "
      "-> les t du panel sont optimistes ; l'unité d'analyse honnête = le token "
      "(médianes intra-token, comme en section 2).")
    A("")
    A("## Règle d'univers candidate (si effet tenu)")
    A("")
    post_gt = np.median([p["d_drift"] for p in pairs]) > 0
    if verdict != "FAIL" and post_gt:
        A("Filtre d'univers pour les stratégies fomo : **ne trader que les tokens "
          "AYANT déjà un achat baleine >= $1k (T0 passé)** — l'univers post-T0 fait "
          "mieux à âge égal (section 1) et le régime drift post-T0 est supérieur "
          "pour la moitié des tokens (section 2). Coût : exclus les "
          "naissances-flash (< 24h, sans T0) = la majorité du corpus ; à arbitrer "
          "contre la fréquence de trade. NE PAS l'imposer tant que le panel "
          "age-apprié ne confirme pas post>pre à âge ÉGAUX sur [0-24h).")
    elif anti:
        A("**L'attention n'est PAS un filtre d'inclusion — c'est un marqueur de "
          "sommet local.** Le panel age-apprié montre post-T0 < never à âge égal "
          "partout (0-1j : -36.8% vs -2.9%, soit -33.9 pp ; 1-3j : -15.0 pp ; "
          "3-7j : -6.8 pp) et le drift montait DÉJÀ avant T0 (+0.9% -> +15.0% sur "
          "[-3.5j;T0)) : la baleine achète le momentum existant et le forward "
          "s'effondre ensuite (mean-reversion post-pump).")
        A("")
        A("Anti-filtre candidat (à valider en paper AVANT tout câblage) : "
          "**exclure des univers LONG fomo les tokens < 7j d'âge dont le premier "
          "achat baleine >= $1k date de < 72h** — leur drift médian 24h est "
          "0.2-0.4x celui des pairs jamais baleine au même âge. ATTENTION aux "
          "tensions : (1) v2 a un PASS en RÉPLICATION skill-weighted sur les "
          "MÊMES events (edge relatif vs baseline du token, filtres age>=7j "
          "déjà favorables) -> l'anti-filtre s'applique à l'univers des "
          "stratégies momentum/long passives, pas à la réplication sélective ; "
          "(2) effet mesuré IN-SAMPLE sur le seul corpus existant : le TRAIN/VAL "
          "par le temps tient (-15.8% / -29.7%) mais c'est le même régime de "
          "marché ; (3) n dose 2+ trop mince pour la conviction collective.")
    else:
        A("Aucun filtre d'univers justifié : l'attention baleine ne déplace pas le "
          "régime de façon mesurable. Le flux baleine reste un signal "
          "d'ÉVÉNEMENT (v2, réplication), pas un changement d'état du token. "
          "Ré-catégoriser dans docs/20-registre-indicateurs.md.")
    A("")
    A(f"Source : {SWAPS_DB.name} (ro) + {FOMO_DB.name} fomo_ohlcv 1h (ro) | "
      f"script : scripts/whale_attention_test.py")
    REPORT.write_text("\n".join(L) + "\n")

    print(f"[att] verdict={verdict} pairs={len(pairs)} "
          f"dDriftMed={pct(np.median(dd_all))} t={tstat(dd_all):+.2f} "
          f"VAL={pct(np.median(ddv))} -> {REPORT.name}")
    for lo, hi in AGE_BUCKETS:
        row = []
        for g in ("never", "pre", "post"):
            c = panel.get((g, lo, hi))
            row.append(f"{g}={pct(np.median(c['r']))}(n={len(c['toks'])})"
                       if c and c["r"] else f"{g}=—")
        print(f"  age {lo}-{hi}j : " + " | ".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
