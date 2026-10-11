#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HOLDOUT-X — les symboles jamais vus du pool v8 (research/hypotheses/holdout-x.md).

La question laissée ouverte par docs/40 : l'edge v8 (+0,093 R, n=868) est-il un
edge réel mais mince, ou du sur-apprentissage de SYMBOLE ? Seule épreuve qui
sépare les deux lectures : appliquer les règles TELLES QUELLES à des perps
Binance USDT-M JAMAIS présentes dans SYMS_40.

## Le gel (AVANT toute collecte — spec holdout-x.md)

- **Univers figé** : HOLDOUT_X ci-dessous = les **48 plus anciennes** perps
  USDT-M (contractType=PERPETUAL, quoteAsset=USDT, status=TRADING,
  onboardDate < 2024-01-01) **hors SYMS_40** (x501_collect_deep40_v31.py:28),
  lues sur fapi exchangeInfo le 2026-10-11 et triées par onboardDate croissant.
  Règle 100 % objectivement datée, choisie AVANT de voir une seule barre —
  on ne choisit pas l'univers après avoir vu les résultats. Aucun produit
  exotique n'entre dans cette tranche (BTCDOMUSDT = 52e, USDCUSDT = 84e :
  hors des 48, aucune exclusion manuelle à justifier).
  Marge de 8 au-dessus du minimum de 40 : contre un échec de COLLECTE
  (données Vision absentes), jamais contre un mauvais résultat — si un
  symbole s'avère inexploitable, il est NOMMÉ dans le rapport du run.
- **BTCUSDT** est ajouté AU RUN (pas dans l'univers) : le moteur le HARDCODE
  comme contexte CHOP D1 (x501_engine_deep_v30.py:907 `SD["BTCUSDT"]`) et son
  timeline sert de grille globale (SYMS[0]). Ses trades sont EXCLUS du verdict
  (BTC ∉ holdout) ; ils restent dans la dynamique du compte, symétriquement
  au run champion.
- **Moteur** : `x501_engine_deep_v30.py` — auto-contenu, versionné, c'est lui
  qui fait foi (spec : « identique bit à bit à x501_alpha_backtest.py »).
  Coûts CFG figés : taker 4,5 bps + slippage 2 bps, TP maker 1,8 bps.

## Le protocole (figé ici, AVANT le run)

- **Fenêtre d'analyse** : entry_time < 2026-10-01T00:00Z — la base champion
  s'arrête au 2026-09-30 ; la collecte holdout peut déborder sur octobre :
  ces barres servent au warmup mais les trades d'octobre sont exclus du
  verdict pour que la comparaison appariée porte sur le MÊME span.
- **Walk-forward protocol_v2 (critère 3)** : 6 fenêtres chrono de 2 mois,
  W1..W6 = 2025-10-01 → 2026-10-01. Window PASS = E[R] de la fenêtre > 0.
  Règles FIGÉES a priori ⇒ rien à calibrer (le critère « calibrage < W_i »
  est trivialement satisfait) ; l'embargo 72 h devient une zone tampon PLUS
  forte : tout trade entré à moins de 72 h d'une borne interne est exclu.
- **IC95** : bootstrap par blocs-mois, 4 000 tirages, seed 7 (reproductible,
  contrairement au display D1 d'audit_check qui n'a pas de seed — ici c'est
  un VERDICT de ledger). Critère : borne basse > 0.
- **Stress ×1,5** (protocol_v2 critère 1) : taker et slippage ×1,5, maker TP
  inchangé. Critère : E[R]_stress > 0.
- **Contrôles** (affichés, non bloquants) : hors top 5 % (par trade R) ;
  base-rate par état = décomposition alpha × fenêtre ; comparaison appariée
  au champion = le MÊME moteur sur SYMS_40, mêmes fenêtres, mêmes coûts.

## Verdict (critères de la spec, figés)

PASS  si E[R] > 0 ET borne basse IC95 > 0 ET n ≥ 400 ET ≥ 5/6 fenêtres PASS
      ET E[R] tient à ×1,5.
FAIL  si borne haute IC95 < +0,05 R.
SOUS_PUISSANT si n < 400.

## Usage

    python3 holdout_x_harness.py --run       # 3 runs moteur (~1 h) + analyse
    python3 holdout_x_harness.py --verdict   # lit le JSON, applique les critères

Collection (harnais ≠ collecteur : le collecteur v31 champion fait le travail,
il accepte --syms= ; la DB est fraîche sur cette machine → l'UNION des deux
univers est collectée ; la table run_log doit exister au préalable car le
collecteur y INSERT sans la créer) :

    mkdir -p "$X501_EXT_ROOT/scripts/x501_v21_results"
    sqlite3 .../om_v27.db "CREATE TABLE IF NOT EXISTS run_log(ts INTEGER, symbol TEXT, layer TEXT, rows INTEGER, note TEXT)"
    X501_EXT_ROOT=<repo> python3 x501_collect_deep40_v31.py --vision --api --funding --qa \
        --syms="BTCUSDT,$(python3 -c 'import holdout_x_harness as H,sys; sys.path.insert(0,"."); print(",".join(dict.fromkeys(H.RUN_SYMS+H.SYMS_40)))')"
"""
from __future__ import annotations

import csv
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXT_ROOT = os.environ.get("X501_EXT_ROOT", str(HERE.parents[2]))
OUT_DIR = Path(os.environ.get(
    "X501_OUT_HOLDOUT", HERE / "results" / "holdout_x"))
RES_JSON = OUT_DIR / "holdout_x_results.json"

# ═══════════════════ LE GEL — univers figé (voir docstring) ═══════════════════
# 48 plus anciennes perps USDT-M (onboardDate < 2024-01-01, status=TRADING)
# hors SYMS_40, triées par onboardDate croissant (fapi exchangeInfo, 11/10).
HOLDOUT_X = [
    "XLMUSDT", "XMRUSDT", "DASHUSDT", "ZECUSDT", "XTZUSDT", "ONTUSDT",
    "IOTAUSDT", "BATUSDT", "NEOUSDT", "QTUMUSDT", "IOSTUSDT", "THETAUSDT",
    "ALGOUSDT", "ZILUSDT", "KNCUSDT", "ZRXUSDT", "COMPUSDT", "KAVAUSDT",
    "BANDUSDT", "RLCUSDT", "SNXUSDT", "SKLUSDT", "YFIUSDT", "CRVUSDT",
    "TRBUSDT", "SUSHIUSDT", "RUNEUSDT", "EGLDUSDT", "ENJUSDT", "KSMUSDT",
    "RSRUSDT", "BELUSDT", "AXSUSDT", "ZENUSDT", "GRTUSDT", "1INCHUSDT",
    "SANDUSDT", "CHZUSDT", "ANKRUSDT", "RVNUSDT", "SFPUSDT", "COTIUSDT",
    "CHRUSDT", "MANAUSDT", "ALICEUSDT", "GTCUSDT", "ONEUSDT", "CELRUSDT",
]
assert len(HOLDOUT_X) == 48 and len(set(HOLDOUT_X)) == 48

SYMS_40 = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT", "DOTUSDT",
    "LTCUSDT", "TRXUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
    "ATOMUSDT", "ETCUSDT", "BCHUSDT", "FILUSDT", "UNIUSDT",
    "AAVEUSDT", "HBARUSDT", "VETUSDT", "ICPUSDT", "FETUSDT",
    "INJUSDT", "LDOUSDT", "GALAUSDT", "IMXUSDT", "STXUSDT",
    "WLDUSDT", "SEIUSDT", "SUIUSDT", "TIAUSDT", "1000PEPEUSDT",
    "1000SHIBUSDT", "1000FLOKIUSDT", "JUPUSDT", "ORDIUSDT"]
assert not (set(HOLDOUT_X) & set(SYMS_40)), "fuite d'un symbole du pool v8"

RUN_SYMS = ["BTCUSDT"] + HOLDOUT_X   # BTC : ancre de grille + contexte CHOP
HOLDOUT_SET = set(HOLDOUT_X)

# Bornes d'analyse et fenêtres protocol_v2 (figées — voir docstring).
CUT_MS = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp() * 1000)
WINDOW_BOUNDS = [2025, 10], [2025, 12], [2026, 2], [2026, 4], \
    [2026, 6], [2026, 8], [2026, 10]
EMBARGO_H = 72
N_BOOT = 4000
SEED = 7


def _ms(y: int, m: int) -> int:
    return int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)


WINDOWS = [(_ms(a, b), _ms(c, d))
           for (a, b), (c, d) in zip(WINDOW_BOUNDS, WINDOW_BOUNDS[1:])]
BOUNDES_INTERNES = [w[0] for w in WINDOWS[1:]]


# ═══════════════════ Analyse (pure — testable sans données) ═══════════════════
def extraire_pool(trades, symboles_autorises: set[str], cut_ms: int = CUT_MS):
    """[(R, entry_ms, alpha, sym)] des trades du pool, hors BTC/contexte,
    hors zone tampon d'embargo aux bornes internes, hors au-delà du CUT."""
    out = []
    for tr in trades:
        sym = tr.key.split(":", 1)[1] if ":" in tr.key else tr.key
        if sym not in symboles_autorises or tr.risk_usd <= 0:
            continue
        if tr.entry_time >= cut_ms:
            continue
        if any(abs(tr.entry_time - b) < EMBARGO_H * 3600 * 1000
               for b in BOUNDES_INTERNES):
            continue
        out.append((tr.pnl / tr.risk_usd, tr.entry_time,
                    tr.key.split(":", 1)[0], sym))
    return out


def ic95_blocs_mois(pool, n_boot: int = N_BOOT, seed: int = SEED):
    """Bootstrap par blocs-mois (bloc = mois calendaire UTC de l'entrée).
    Retourne (borne_basse, borne_haute, E[R], n)."""
    par_mois: dict[str, list[float]] = {}
    for r, t, _, _ in pool:
        m = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m")
        par_mois.setdefault(m, []).append(r)
    mois = sorted(par_mois)
    if not mois:
        return None, None, 0.0, 0
    rng = random.Random(seed)
    n = len(pool)
    e_r = sum(r for r, *_ in pool) / n
    moyennes = []
    for _ in range(n_boot):
        tot = 0.0
        for _ in range(len(mois)):
            tot += sum(par_mois[rng.choice(mois)])
        moyennes.append(tot / n)
    moyennes.sort()
    lo = moyennes[int(0.025 * n_boot)]
    hi = moyennes[int(0.975 * n_boot)]
    return lo, hi, e_r, n


def fenetres(pool):
    """E[R] par fenêtre protocol_v2 + le nombre de PASS."""
    par_w = []
    for lo, hi in WINDOWS:
        rs = [r for r, t, _, _ in pool if lo <= t < hi]
        e = sum(rs) / len(rs) if rs else None
        par_w.append({"n": len(rs), "e_r": None if e is None else round(e, 4),
                      "pass": bool(e is not None and e > 0)})
    return {"bornes": [[datetime.fromtimestamp(lo / 1000, timezone.utc).strftime("%Y-%m-%d"),
                        datetime.fromtimestamp(hi / 1000, timezone.utc).strftime("%Y-%m-%d")]
                       for lo, hi in WINDOWS],
            "detail": par_w,
            "n_pass": sum(1 for w in par_w if w["pass"])}


def hors_top5(pool):
    """E[R] sans les 5 % meilleurs trades (par R) — un trade ne porte pas."""
    rs = sorted((r for r, *_ in pool), reverse=True)
    k = max(1, int(len(rs) * 0.05))
    reste = rs[k:]
    return {"n_coupe": k, "e_r_sans_top5": round(sum(reste) / len(reste), 4)
            if reste else None}


def par_etat(pool):
    """Base-rate par état : E[R] par alpha × fenêtre (MAGNITUDE ≠ DIRECTION :
    on regarde si un seul alpha/fenêtre porte tout)."""
    etats = {}
    for i, (lo, hi) in enumerate(WINDOWS, 1):
        for a in ("A1", "A2", "A3", "A4"):
            rs = [r for r, t, al, _ in pool if al == a and lo <= t < hi]
            if rs:
                etats[f"W{i}/{a}"] = {"n": len(rs),
                                      "e_r": round(sum(rs) / len(rs), 4)}
    return etats


def resume_pool(pool, label: str) -> dict:
    lo, hi, e_r, n = ic95_blocs_mois(pool)
    return {"label": label, "n": n, "e_r": round(e_r, 4) if n else None,
            "ic95": [None if lo is None else round(lo, 4),
                     None if hi is None else round(hi, 4)],
            "fenetres": fenetres(pool),
            "hors_top5": hors_top5(pool),
            "par_etat": par_etat(pool)}


# ═══════════════════ Les 3 runs moteur ═══════════════════
MIN_JOURS = 66          # 60 j warmup + 24 barres + marge — sinon StopIteration


def check_data() -> list[str]:
    """Chaque symbole des DEUX univers (holdout + champion) doit avoir des
    klines deep exploitables. Un symbole insuffisant est NOMMÉ (exclusion de
    DISPONIBILITÉ, jamais de résultat) — le moteur crasherait sinon
    (load_klines RuntimeError / warmup StopIteration). Retourne les
    exploitables dans l'ordre RUN_SYMS puis SYMS_40 (BTC déjà en tête)."""
    import sqlite3
    tous = list(dict.fromkeys(RUN_SYMS + SYMS_40))
    db = sqlite3.connect(f"{EXT_ROOT}/scripts/x501_v21_results/om_v27.db")
    bons, mauvais = [], []
    for s in tous:
        row = db.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM "
                         "bn_kline_1h_deep WHERE symbol=?", (s,)).fetchone()
        n, t0, t1 = row
        jours = (t1 - t0) / 86400000 if t0 else 0
        (bons if n > 0 and jours >= MIN_JOURS else mauvais).append(
            (s, n, round(jours)))
    db.close()
    if mauvais:
        print("SYMBOLES INEXPLOITABLES (exclusion de disponibilité, nommés) :")
        for s, n, j in mauvais:
            print(f"  {s:16} n={n} span={j} j (< {MIN_JOURS} j)")
    n_h = len([s for s, _, _ in bons if s in HOLDOUT_SET])
    print(f"[data] {len(bons)}/{len(tous)} symboles exploitables "
          f"(>= {MIN_JOURS} j) dont {n_h} holdout")
    return [s for s, _, _ in bons]


def run_moteur():
    os.environ.setdefault("X501_EXT_ROOT", EXT_ROOT)
    os.environ["X501_EXT_ROOT"] = EXT_ROOT
    os.environ["X501_OUT"] = str(OUT_DIR)
    sys.path.insert(0, str(HERE))
    import x501_engine_deep_v30 as eng  # lit X501_EXT_ROOT à l'import

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Garde de disponibilité AVANT tout run (jamais de saut silencieux).
    bons = check_data()
    bons_set = set(bons)
    holdout_ok = [s for s in RUN_SYMS if s in bons_set]     # BTC déjà en tête
    if len([s for s in holdout_ok if s in HOLDOUT_SET]) < 40:
        raise SystemExit("moins de 40 symboles holdout exploitables — la "
                         "spec exige >= 40 ; compléter la collecte, ne pas "
                         "abaisser l'univers")
    champion_ok = [s for s in SYMS_40 if s in bons_set]

    resultats = {}

    def ecrit(trades, label):
        p = OUT_DIR / f"holdout_x_trades_{label}.csv"
        with open(p, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["key", "side", "entry_time", "exit_time", "entry",
                        "exit_avg", "risk_usd", "pnl", "reason"])
            for tr in trades:
                w.writerow([tr.key, tr.side, tr.entry_time, tr.exit_time,
                            tr.entry, tr.exit_avg, tr.risk_usd, tr.pnl,
                            tr.reason])
        return p

    # RUN 1 — holdout nominal (BTC = ancre + contexte, trades exclus au verdict)
    eng.SYMS = holdout_ok  # exploitables, BTC d'abord (ancre de grille)
    print(f"[holdout] RUN 1/3 nominal : {len(RUN_SYMS)} symboles", flush=True)
    res_h = eng.run_portfolio()
    ecrit(res_h["trades"], "holdout")
    pool_h = extraire_pool(res_h["trades"], HOLDOUT_SET)
    resultats["holdout"] = resume_pool(pool_h, "holdout")
    resultats["holdout"]["trades_bruts"] = len(res_h["trades"])
    resultats["holdout"]["frais"] = round(res_h["total_fees"], 2)
    resultats["holdout"]["funding"] = round(res_h["total_funding"], 2)
    resultats["holdout"]["liq"] = res_h["liq_hits"]

    # RUN 2 — champion apparié : le MÊME moteur sur SYMS_40 (contrôle)
    eng.SYMS = champion_ok
    print(f"[holdout] RUN 2/3 champion apparié ({len(champion_ok)} symboles)", flush=True)
    res_c = eng.run_portfolio()
    ecrit(res_c["trades"], "champion")
    pool_c = extraire_pool(res_c["trades"], set(SYMS_40))
    resultats["champion"] = resume_pool(pool_c, "champion")
    resultats["champion"]["trades_bruts"] = len(res_c["trades"])

    # RUN 3 — holdout stress : taker et slippage ×1,5, maker TP inchangé
    eng.SYMS = holdout_ok
    eng.CFG["taker"] = round(eng.CFG["taker"] * 1.5, 6)
    eng.CFG["slip"] = round(eng.CFG["slip"] * 1.5, 6)
    print(f"[holdout] RUN 3/3 stress ×1,5 (taker={eng.CFG['taker']}, "
          f"slip={eng.CFG['slip']})", flush=True)
    res_s = eng.run_portfolio()
    ecrit(res_s["trades"], "holdout_stress")
    pool_s = extraire_pool(res_s["trades"], HOLDOUT_SET)
    resultats["holdout_stress"] = {
        "label": "holdout_stress", "n": len(pool_s),
        "e_r": round(sum(r for r, *_ in pool_s) / len(pool_s), 4)
        if pool_s else None}

    resultats["gel"] = {
        "univers": HOLDOUT_X, "n_univers": len(HOLDOUT_X),
        "regle": "48 plus anciennes perps USDT-M (onboardDate < 2024-01-01, "
                 "status=TRADING) hors SYMS_40, fapi exchangeInfo 11/10",
        "cut_analyse": "2026-10-01T00:00Z",
        "fenetres": resultats["holdout"]["fenetres"]["bornes"],
        "embargo_h": EMBARGO_H, "n_boot": N_BOOT, "seed": SEED,
    }
    RES_JSON.write_text(json.dumps(resultats, indent=1, ensure_ascii=False),
                        encoding="utf-8")
    print(f"OK -> {RES_JSON}", flush=True)


# ═══════════════════ Verdict ═══════════════════
def verdict():
    d = json.loads(RES_JSON.read_text(encoding="utf-8"))
    h, s, c = d["holdout"], d["holdout_stress"], d["champion"]
    lo, hi = h["ic95"]
    n_pass = h["fenetres"]["n_pass"]
    print(f"HOLDOUT-X — {h['n']} trades (bruts {h['trades_bruts']}) · "
          f"champion apparié {c['n']} trades")
    print(f"  E[R] holdout {h['e_r']:+.4f}  IC95 [{lo}, {hi}]")
    print(f"  fenêtres PASS : {n_pass}/6")
    print(f"  stress ×1,5 : E[R] {s['e_r']:+.4f} (n={s['n']})")
    print(f"  hors top 5 % : E[R] {h['hors_top5']['e_r_sans_top5']:+.4f} "
          f"(coupe {h['hors_top5']['n_coupe']})")
    print(f"  champion apparié : E[R] {c['e_r']:+.4f} IC95 {c['ic95']}")
    pire = min(h["par_etat"].items(), key=lambda kv: kv[1]["e_r"],
               default=None)
    if pire:
        print(f"  pire état : {pire[0]} E[R] {pire[1]['e_r']:+.4f} "
              f"(n={pire[1]['n']})")

    if h["n"] < 400:
        v = "SOUS_PUISSANT"
        print(f"\nVERDICT : {v} — n={h['n']} < 400 (l'edge détectable IC95 "
              "dépasse +0,10 R : on ne conclut pas)")
    elif h["e_r"] is not None and (hi is not None and hi < 0.05):
        v = "FAIL"
        print(f"\nVERDICT : {v} — borne haute IC95 {hi} < +0,05 R")
    elif (h["e_r"] is not None and h["e_r"] > 0 and lo is not None
            and lo > 0 and n_pass >= 5 and s["e_r"] is not None
            and s["e_r"] > 0):
        v = "PASS"
        print("\nVERDICT : PASS — l'edge v8 tient sur des symboles jamais vus")
    else:
        v = "FAIL"
        print("\nVERDICT : FAIL — au moins un critère PASS n'est pas rempli")
    print("\nbloc ledger :")
    print(f"  python3 scripts/lab_ledger.py log holdout-x {v} "
          f"--n {h['n']} --er {h['e_r']} --note "
          f"\"holdout-x moteur deep v30, {len(HOLDOUT_X)} symboles jamais vus, "
          f"IC95 [{lo},{hi}], {n_pass}/6 fenêtres, stress {s['e_r']:+.4f}, "
          f"champion apparié {c['e_r']:+.4f}\"")
    return 0


if __name__ == "__main__":
    if "--run" in sys.argv:
        run_moteur()
    elif "--verdict" in sys.argv:
        raise SystemExit(verdict())
    else:
        print(__doc__)
