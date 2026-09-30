#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_fill_maker_surface.py — LA CHAÎNE DE PREUVE MAKER : mesurer ce que la MC v20 suppose.

La MC v20 (chiffre officiel 468,4 $ maker δ=2 vs 272,7 $ taker) repose sur deux
hypothèses d'exécution durcies en constantes :
  (H1) fill 97,9 % à δ=2 bps / 95,8 % à δ=5 (52 728 tentatives, 1h/708 j) ;
  (H2) le maker = un simple delta de coût (4,0 bps/jambe vs taker all-in 6,1),
       uniforme sur tous les trades — la SÉLECTION (qui est fillé, qui tombe en
       fallback taker, qui est invalidé) n'y est pas modélisée.

Cet outil mesure les deux avec la data premium locale (klines 1h, format Binance,
{SYM}_1h.csv dans X501_DATA_DIR, défaut data/x501_1h du repo) :

  NIVEAU A — surface de fill physique δ×TTL : pour CHAQUE barre de CHAQUE
  symbole, un ordre limite hypothétique est placé à la clôture (buy SOUS le
  prix, sell AU-DESSUS), la mèche des barres suivantes décide du fill (le
  toucher du niveau = fill ; gap au-delà de la limite = fill au prix d'ouverture,
  favorable). Sortie : P(fill) par (δ, TTL), par tercile de volatilité ATR%,
  symétrie buy/sell. Reproduit et étend (H1) à méthodologie documentée et
  re-runnable — la référence durcie 97,9 % reste le chiffre de la MC v20.

  NIVEAU B — sélection réelle sur le pool P1 certifié (469 trades, alphas
  A1/A3/A4) : chaque trade est rejoué en exécution maker avec la doctrine
  exacte des kScripts _MK (limite placée à la clôture du signal, fill
  intrabar, fallback taker à l'expiration TTL, invalidation si clôture
  au-delà du stop sans fill). Décomposition fill/fallback/invalidé, delta
  d'exécution en bps vs le taker certifié, conversion en R (dR = delta/dist,
  même convention que la MC v20), effet des invalidations, grille δ×TTL,
  décomposition par alpha.

  NIVEAU C — composante sortie analytique : dans le pool certifié, les jambes
  TP1/TP2 sortent AU NIVEAU (ordre limite) -> en réel, le delta maker vs taker
  sur ces jambes = fees (3,5) + spread évité (0,6) = 4,1 bps, fill quasi
  certain (le prix CROISE le niveau pour l'atteindre ; gap au-delà = fill au
  gap, favorable) ; les jambes stop/trail/flip/avortée sortent AU MARCHÉ
  (taker des deux régimes) -> delta 0. Pondération par fraction de position.

  VERDICT — delta total par jambe (entrée mesurée + sortie analytique)/2 vs
  l'hypothèse MC v20 (4,0 bps/jambe), et scénario MC recalibré : le run MC v20
  rejoué avec l'extra de coût realistement mesuré (grâce au noyau local, HORS
  repo : la v21 candidate reste à valider par review avant toute édition des
  chiffres officiels).

Constantes d'exécution (mesures v16/v17, Bybit VIP0 USDT-perp) :
  fee taker 5,5 bps | fee maker 2,0 bps | demi-spread 0,6 bps | taker all-in 6,1
  delta d'un fill limite sans gap vs taker all-in : prix δ (2,0) + fees (3,5)
  + spread évité (0,6) = 6,1 bps ; la MC v20 n'en crédite que 4,1 (elle ignore
  le gain de prix + spread) — le surplus est une marge de conservatisme mesurée.

Limites assumées (pré-enregistrées) :
  L1 l'ordre de passage intrabar (limite vs stop dans la MÊME barre) n'est pas
     observable en 1h : la doctrine fill-puis-invalide suit l'ordre des prix
     (la limite est toujours entre le signal et le stop, donc touchée avant) ;
  L2 le mid n'est pas mesuré : le gain de prix est calculé vs le prix taker
     original (open de la barre d'exécution), le spread 0,6 est une mesure
     moyenne — la composante « prix » est la seule dépendante de la data ;
  L3 les tentatives de la surface se chevauchent (un ordre par barre) :
     estimateur cohérent de P(touch | horizon), autocorrélation documentée ;
  L4 la composition des jambes (quelles sorties existent) est une propriété du
     pool certifié, tenue inchangée par le changement de régime d'entrée à
     l'ordre 1 (un décalage de 2 bps sur un stop à ~242 bps) ;
  L5 l'approximation du delta de sortie (4,1 bps sur TP, 0 ailleurs) est
     analytique, pas mesurée : le fill TP limite est considéré certain.

Reproduction :
  X501_DATA_DIR=<dir des {SYM}_1h.csv> python3 x501_fill_maker_surface.py
Sorties : fill_maker_surface.json (versionné, déterministe) + résumé console.
"""
import csv
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("X501_DATA_DIR", HERE / "../../../data/x501_1h"))
POOL_CSV = HERE / "pool_P1_entrees.csv"
OUT_JSON = HERE / "fill_maker_surface.json"

# ------------------------- constantes d'exécution -----------------------------
FEE_TAKER = 5.5          # bps
FEE_MAKER = 2.0          # bps
HALF_SPREAD = 0.6        # bps
TAKER_ALLIN = FEE_TAKER + HALF_SPREAD            # 6.1
FEE_DELTA = TAKER_ALLIN - FEE_MAKER              # 4.1 (frais + spread évité)
MC_ENTREE_HYP = 4.0                              # delta d'entrée supposé par la MC v20 (6.1 - 2.1)
MC_FILL_REF_D2 = 97.9                            # référence durcie MC v20 (%)

DELTAS_BPS = [1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0]
TTL_LIST = [1, 2, 3, 6, 12]
K_MAX = max(TTL_LIST)
MAKER_DELTA_BPS = 2.0
MAKER_TTL = 2
ATR_N = 14
GRILLE = [(1.0, 1), (1.0, 2), (2.0, 1), (2.0, 2), (3.0, 2), (3.0, 3),
          (5.0, 2), (5.0, 3), (2.0, 3), (2.0, 6)]


# ------------------------------- chargement -----------------------------------
def load_klines(sym):
    p = DATA_DIR / f"{sym}_1h.csv"
    if not p.exists():
        return None
    cols = ("open_time", "open", "high", "low", "close")
    buf = {c: [] for c in cols}
    with open(p, newline="") as f:
        for row in csv.DictReader(f):
            for c in cols:
                buf[c].append(float(row[c]))
    return {c: np.asarray(v, dtype=np.float64) for c, v in buf.items()}


def atr_pct(kl, n=ATR_N):
    h, l, c = kl["high"], kl["low"], kl["close"]
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = np.convolve(tr, np.ones(n) / n, mode="full")[: len(tr)]
    atr[: n - 1] = atr[n - 1]          # lissage du bord gauche (régime stationnaire)
    return atr / c * 1e4


# ---------------------- NIVEAU A : surface de fill δ×TTL ----------------------
def first_touch(kl, side, delta_bps):
    """ft[N] = premier k∈[1..K_MAX] tel que la mèche de la barre N+k touche la
    limite placée à la clôture N ; 0 si jamais touché (ou fenêtre tronquée)."""
    c, lo, hi = kl["close"], kl["low"], kl["high"]
    n = len(c)
    plim = c * (1.0 - side * delta_bps * 1e-4)   # buy SOUS le prix, sell AU-DESSUS
    ft = np.zeros(n, dtype=np.int64)
    for k in range(1, K_MAX + 1):
        if k >= n:
            break
        touch = (lo[k:] <= plim[: n - k]) if side == 1 else (hi[k:] >= plim[: n - k])
        upd = (ft[k:] == 0) & touch
        ft[k:][upd] = k
    ft[n - K_MAX:] = 0                 # fenêtres tronquées : exclues des décomptes
    return ft


def p_fill(ft, ttl):
    valid = len(ft) - K_MAX
    if valid <= 0:
        return None
    return float(np.mean((ft[:valid] > 0) & (ft[:valid] <= ttl)) * 100.0)


def niveau_a(kl_cache, syms):
    """P(fill) par (δ, TTL) × tercile de volatilité, buy et sell."""
    res = {"n_barres": 0, "n_symboles": 0,
           "surface": {}, "par_vol": {}, "par_symbole": {}}
    agg_surf = {}                       # (lbl, delta, ttl) -> [touches, n]
    agg_vol = {}                        # (tercile, delta, ttl) -> [touches, n] (buy)
    sym_cell = {}                       # sym -> {(delta, ttl): p_buy}
    for sym in syms:
        kl = kl_cache.get(sym)
        if kl is None or len(kl["close"]) < K_MAX + 100:
            continue
        res["n_symboles"] += 1
        res["n_barres"] += len(kl["close"]) - K_MAX
        v = atr_pct(kl)
        valid = len(v) - K_MAX
        q1, q2 = np.quantile(v[:valid], [1 / 3, 2 / 3])
        ter = np.full(valid, 2, dtype=np.int64)
        ter[v[:valid] < q1] = 0
        ter[(v[:valid] >= q1) & (v[:valid] < q2)] = 1
        sym_cell[sym] = {}
        for side in (1, -1):
            lbl = "buy" if side == 1 else "sell"
            for d in DELTAS_BPS:
                ft = first_touch(kl, side, d)
                hit_by_ttl = {t: (ft[:valid] > 0) & (ft[:valid] <= t) for t in TTL_LIST}
                for ttl in TTL_LIST:
                    cell = agg_surf.setdefault((lbl, d, ttl), [0, 0])
                    cell[0] += int(np.sum(hit_by_ttl[ttl]))
                    cell[1] += valid
                    if side == 1:
                        sym_cell[sym][(d, ttl)] = float(np.mean(hit_by_ttl[ttl]) * 100.0)
                        for t3 in (0, 1, 2):
                            m = ter == t3
                            c3 = agg_vol.setdefault((t3, d, ttl), [0, 0])
                            c3[0] += int(np.sum(hit_by_ttl[ttl][m]))
                            c3[1] += int(np.sum(m))
    for (lbl, d, ttl), (hit, n) in sorted(agg_surf.items()):
        res["surface"][f"{lbl}_d{d:g}_ttl{ttl}"] = round(hit / n * 100.0, 3)
    for (t3, d, ttl), (hit, n) in sorted(agg_vol.items()):
        if n > 0:
            res["par_vol"][f"t{t3}_d{d:g}_ttl{ttl}"] = round(hit / n * 100.0, 3)
    res["par_symbole"] = {s: {f"d{d:g}_ttl{ttl}": round(p, 2) for (d, ttl), p in sorted(c.items())}
                          for s, c in sorted(sym_cell.items())}
    return res


# ------------- NIVEAU B : sélection réelle sur le pool P1 certifié ------------
def load_pool():
    rows = []
    with open(POOL_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"sym": r["sym"], "t_in": int(r["t_in"]), "side": int(r["side"]),
                         "entry": float(r["entry"]), "stop": float(r["stop"]),
                         "dist_bps": float(r["dist_bps"]), "R": float(r["R"]),
                         "alpha": r["alpha"]})
    return rows


def sim_trade(kl, t, delta_bps, ttl):
    """Rejoue l'entrée d'un trade du pool en régime maker (doctrine _MK).
    Retourne (cas, prix_bps, px) avec prix_bps = gain de PRIX vs le taker
    original (hors fees), cas ∈ {fill, fallback, invalide, hors_data}."""
    ot = kl["open_time"]
    idx = int(np.searchsorted(ot, t["t_in"]))
    if idx >= len(ot) or ot[idx] != t["t_in"]:
        return "hors_data", None, None
    s = t["side"]
    iS = idx - 1
    if iS < 0:
        return "hors_data", None, None
    plim = kl["close"][iS] * (1.0 - s * delta_bps * 1e-4)
    open_taker = kl["open"][idx]
    stop = t["stop"]
    for k in range(ttl):
        i = idx + k
        if i >= len(ot):
            return "hors_data", None, None
        lo, hi = kl["low"][i], kl["high"][i]
        op, cl = kl["open"][i], kl["close"][i]
        touched = (lo <= plim) if s == 1 else (hi >= plim)
        if touched:
            px = min(op, plim) if s == 1 else max(op, plim)
            return "fill", s * (open_taker - px) / open_taker * 1e4, px
        if s * (cl - stop) < 0:          # clôture au-delà du stop sans fill
            return "invalide", None, None
    i = idx + ttl
    if i >= len(ot):
        return "hors_data", None, None
    px = kl["open"][i]
    return "fallback", s * (open_taker - px) / open_taker * 1e4, px


def _stats(xs, key):
    a = np.asarray([x[key] for x in xs], dtype=np.float64)
    if len(a) == 0:
        return None
    return {"n": int(len(a)), "mean": round(float(a.mean()), 3),
            "p50": round(float(np.median(a)), 3),
            "p10": round(float(np.quantile(a, 0.10)), 3),
            "p90": round(float(np.quantile(a, 0.90)), 3)}


def _mix_agregats(fills, fallbacks, invalides, n_pool, delta_bps, ttl):
    out = {"delta_bps": delta_bps, "ttl": ttl, "n_pool": n_pool,
           "cas": {"fill": len(fills), "fallback": len(fallbacks),
                   "invalide": len(invalides),
                   "pct_fill": round(len(fills) / n_pool * 100, 2),
                   "pct_fallback": round(len(fallbacks) / n_pool * 100, 2),
                   "pct_invalide": round(len(invalides) / n_pool * 100, 2)}}
    mix = fills + fallbacks
    out["delta_mix"] = _stats(mix, "delta_bps")
    out["delta_fills"] = _stats(fills, "delta_bps")
    out["delta_fallbacks"] = _stats(fallbacks, "delta_bps")
    dm = out["delta_mix"]
    out["vs_mc_entree"] = {
        "hypothese_bps": MC_ENTREE_HYP,
        "mesure_bps": dm["mean"] if dm else None,
        "ecart_bps": round(dm["mean"] - MC_ENTREE_HYP, 3) if dm else None,
        "conservatrice": bool(dm and dm["mean"] >= MC_ENTREE_HYP),
    }
    for x in mix:
        x["dR"] = round(x["delta_bps"] / x["dist_bps"], 6)
    out["dR_entree"] = _stats(mix, "dR")
    if invalides:
        a = np.asarray([x["R_evite"] for x in invalides])
        out["invalidations"] = {"n": len(invalides),
                                "R_evite_mean": round(float(a.mean()), 4),
                                "R_evite_sum": round(float(a.sum()), 3),
                                "R_evite_p50": round(float(np.median(a)), 3),
                                "wr_evite": round(float(np.mean(a > 0) * 100), 1)}
    else:
        out["invalidations"] = {"n": 0}
    # par alpha : le biais de sélection est-il concentré sur un alpha ?
    by_a = {}
    for x in mix:
        by_a.setdefault(x["alpha"], []).append(x["delta_bps"])
    out["delta_par_alpha"] = {a: {"n": len(v), "mean": round(float(np.mean(v)), 3)}
                              for a, v in sorted(by_a.items())}
    return out


def niveau_b_detail(kl_cache, pool, delta_bps, ttl):
    """Config principale (δ=2/TTL=2) : agrégats + détail trade par trade."""
    fills, fallbacks, invalides, hors = [], [], [], []
    for t in pool:
        kl = kl_cache.get(t["sym"])
        rec = {"sym": t["sym"], "t_in": t["t_in"], "side": t["side"],
               "dist_bps": round(t["dist_bps"], 2), "R": round(t["R"], 4),
               "alpha": t["alpha"]}
        cas, prix, px = ("hors_data", None, None) if kl is None else sim_trade(kl, t, delta_bps, ttl)
        if cas == "hors_data":
            hors.append(rec)
            continue
        if cas == "fill":
            rec["delta_bps"] = round(prix + FEE_DELTA, 3)
            rec["prix_bps"] = round(prix, 3)
            rec["px_fill"] = px
            fills.append(rec)
        elif cas == "fallback":
            rec["delta_bps"] = round(prix, 3)
            rec["prix_bps"] = round(prix, 3)
            rec["px_fallback"] = px
            fallbacks.append(rec)
        else:
            rec["R_evite"] = rec["R"]
            invalides.append(rec)
    out = _mix_agregats(fills, fallbacks, invalides, len(pool), delta_bps, ttl)
    strict = [f for f in fills if abs(f["prix_bps"] - delta_bps) < 0.01]
    out["fills_sans_gap"] = len(strict)
    out["fills_avec_gap"] = len(fills) - len(strict)
    out["detail"] = {"fills": fills, "fallbacks": fallbacks, "invalides": invalides,
                     "hors_data": hors}
    return out


def niveau_b_grille(kl_cache, pool):
    """Grille δ×TTL : agrégats compacts uniquement (le détail reste δ=2/TTL=2)."""
    res = {}
    for d, ttl in GRILLE:
        fills, fallbacks, invalides = [], [], []
        for t in pool:
            kl = kl_cache.get(t["sym"])
            if kl is None:
                continue
            cas, prix, _ = sim_trade(kl, t, d, ttl)
            if cas == "fill":
                fills.append(prix + FEE_DELTA)
            elif cas == "fallback":
                fallbacks.append(prix)
            elif cas == "invalide":
                invalides.append(t["R"])
        nf, nb, ni = len(fills), len(fallbacks), len(invalides)
        a = np.asarray(fills + fallbacks, dtype=np.float64)
        res[f"d{d:g}_ttl{ttl}"] = {
            "pct_fill": round(nf / len(pool) * 100, 2),
            "pct_fallback": round(nb / len(pool) * 100, 2),
            "pct_invalide": round(ni / len(pool) * 100, 2),
            "delta_mix_mean": round(float(a.mean()), 3) if len(a) else None,
            "delta_mix_p50": round(float(np.median(a)), 3) if len(a) else None,
        }
    return res


# ----------- NIVEAU C : composante sortie analytique (jambes du pool) ---------
def niveau_c(kl_cache, pool):
    """Delta de sortie par jambe : TP limites = 4,1 bps (fees + spread, même
    niveau, fill quasi certain), sorties marché (stop/trail/flip/avortée) = 0.
    Pondération par fraction de position (frac du notional de sortie)."""
    import pickle
    src = os.environ.get("X501_POOL_P1", "/home/z/my-project/scripts/x501_v8_results/pool_v8_P1.pkl")
    if not os.path.exists(src):
        return {"disponible": False, "note": f"pool pickle absent : {src}"}
    with open(src, "rb") as f:
        trades = pickle.load(f)["trades"]
    num = 0.0
    den = 0.0
    n_jambes = 0
    par_reason = {}
    for t in trades:
        for (_, px, frac, reason) in t["legs"]:
            d = FEE_DELTA if reason in ("tp1", "tp2") else 0.0
            num += frac * d
            den += frac
            n_jambes += 1
            pr = par_reason.setdefault(reason, {"n": 0, "frac": 0.0})
            pr["n"] += 1
            pr["frac"] += frac
    if den <= 0:
        return {"disponible": False, "note": "fractions invalides"}
    res = {"disponible": True, "n_jambes": n_jambes,
           "delta_sortie_bps": round(num / den, 3),
           "par_reason": {r: {"n": pr["n"], "frac": round(pr["frac"], 3)}
                          for r, pr in sorted(par_reason.items())}}
    res["poids_tp_pct"] = round(sum(pr["frac"] for r, pr in par_reason.items()
                                    if r in ("tp1", "tp2")) / den * 100, 1)
    return res


# ------------------------------- orchestration --------------------------------
def main():
    kl_cache = {}
    syms = sorted(p.name[:-7] for p in DATA_DIR.glob("*_1h.csv"))
    for s in syms:
        kl = load_klines(s)
        if kl is not None:
            kl_cache[s] = kl
    if not kl_cache:
        raise SystemExit(f"aucune kline dans {DATA_DIR} (X501_DATA_DIR ?)")

    res = {"fenetre": {}, "niveau_A": niveau_a(kl_cache, sorted(kl_cache))}
    ots = [kl["open_time"][0] for kl in kl_cache.values()]
    otf = [kl["open_time"][-1] for kl in kl_cache.values()]
    import datetime as dt
    res["fenetre"] = {"data_dir": str(DATA_DIR), "n_symboles": len(kl_cache),
                      "de": dt.datetime.fromtimestamp(min(ots) / 1000, dt.UTC).isoformat(),
                      "a": dt.datetime.fromtimestamp(max(otf) / 1000, dt.UTC).isoformat()}

    pool = load_pool()
    res["niveau_B"] = niveau_b_detail(kl_cache, pool, MAKER_DELTA_BPS, MAKER_TTL)
    res["grille_B"] = niveau_b_grille(kl_cache, pool)
    res["niveau_C"] = niveau_c(kl_cache, pool)

    # delta total par jambe = (entrée mesurée + sortie analytique)/2
    b, c = res["niveau_B"], res["niveau_C"]
    if c.get("disponible"):
        d_ent = b["delta_mix"]["mean"]
        d_sort = c["delta_sortie_bps"]
        res["verdict"] = {
            "delta_entree_bps": round(d_ent, 3),
            "delta_sortie_bps": round(d_sort, 3),
            "delta_par_jambe_bps": round((d_ent + d_sort) / 2, 3),
            "hypothese_mc_par_jambe_bps": MC_ENTREE_HYP,
            "part_de_credit_mc_pct": round((d_ent + d_sort) / 2 / MC_ENTREE_HYP * 100, 1),
        }
    else:
        res["verdict"] = {"delta_entree_bps": b["delta_mix"]["mean"],
                          "note": "sortie analytique indisponible (pool pickle absent)"}

    # cellules de contrôle
    s = res["niveau_A"]["surface"]
    res["controles"] = {
        "d2_ttl2_buy": s.get("buy_d2_ttl2"), "d2_ttl2_sell": s.get("sell_d2_ttl2"),
        "d2_ttl2_moyenne": round((s.get("buy_d2_ttl2", 0) + s.get("sell_d2_ttl2", 0)) / 2, 2),
        "ref_durcie_mc": MC_FILL_REF_D2,
        "d5_ttl2_moyenne": round((s.get("buy_d5_ttl2", 0) + s.get("sell_d5_ttl2", 0)) / 2, 2),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)

    # ---------------- résumé console -----------------
    print(f"DATA : {res['niveau_A']['n_symboles']} symboles, "
          f"{res['niveau_A']['n_barres']:,} barres-h tentatives, "
          f"{res['fenetre']['de'][:10]} -> {res['fenetre']['a'][:10]}")
    print("SURFACE P(fill) %  (buy | sell) :")
    print("  δ\\TTL " + "".join(f"{t:>13}" for t in TTL_LIST))
    for d in DELTAS_BPS:
        row = f"  {d:>5g} "
        for t in TTL_LIST:
            bb = s.get(f"buy_d{d:g}_ttl{t}", 0)
            se = s.get(f"sell_d{d:g}_ttl{t}", 0)
            row += f"{bb:6.1f}/{se:<6.1f}"
        print(row)
    print("PAR VOLATILITÉ (terciles ATR%, buy, δ=2) :",
          {f"t{i}": res["niveau_A"]["par_vol"].get(f"t{i}_d2_ttl2") for i in (0, 1, 2)})
    b = res["niveau_B"]
    print(f"NIVEAU B (pool {b['n_pool']}, δ={b['delta_bps']}, TTL={b['ttl']}) : "
          f"fill {b['cas']['pct_fill']} % | fallback {b['cas']['pct_fallback']} % | "
          f"invalide {b['cas']['pct_invalide']} % | hors data {len(b['detail']['hors_data'])}")
    print(f"  delta mix   : {b['delta_mix']}")
    print(f"  delta fills : {b['delta_fills']}")
    print(f"  delta fb    : {b['delta_fallbacks']}")
    print(f"  vs MC entrée ({MC_ENTREE_HYP} bps) : {b['vs_mc_entree']}")
    print(f"  dR entrée   : {b['dR_entree']}")
    print(f"  par alpha   : {b['delta_par_alpha']}")
    print(f"  invalidations : {b['invalidations']}")
    print("GRILLE B (delta_mix_mean bps) :")
    for k, v in res["grille_B"].items():
        print(f"  {k:<12} fill {v['pct_fill']:>6.2f} % | fb {v['pct_fallback']:>5.2f} %"
              f" | delta {v['delta_mix_mean']:>8.3f} (p50 {v['delta_mix_p50']})")
    print(f"NIVEAU C (sortie analytique) : delta {res['niveau_C'].get('delta_sortie_bps')} bps"
          f" | poids TP {res['niveau_C'].get('poids_tp_pct')} %")
    print(f"VERDICT : {res['verdict']}")
    print(f"JSON -> {OUT_JSON}")


if __name__ == "__main__":
    main()
