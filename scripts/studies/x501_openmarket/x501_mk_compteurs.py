#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501_mk_compteurs.py — LA BOUCLE DE SURVEILLANCE MAKER : les compteurs _MK -> verdict.

La mesure historique (fill_maker_surface.json : fill 93,82 % à δ=2/TTL=2 sur les
signaux du pool P1, 440 fills / 29 fallbacks / 0 invalidation) est une mesure
PASSEE. La preuve que le régime maker tient en VRAIE exécution passe par les
compteurs internes des kScripts _MK, conçus pour ça :
  mkFills  = fills maker            mkFb     = fills en fallback taker
  mkTOut   = expirations TTL sans fallback (trade abandonné)
  mkInv    = invalidations (clôture au-delà du stop prévu)
Les deux kScripts _MK les rapportent au rapport fin de run (isLastBar) et dans
les variables du chart : ce parseur transforme un relevé en VERDICT.

FORMAT DU RELEVÉ (CSV, une ligne par run/rélevé, encodage UTF-8, séparateur ,) :
  date_iso,symbole,timeframe,mkFills,mkFb,mkTOut,mkInv,fallback_on
  2026-10-05,BTCUSDT,H1,31,2,1,0,1
  (date_iso libre mais OBLIGATOIRE, symbole libre, timeframe H1/H4,
   fallback_on 0/1 = l'input fallbackTaker du run)

VERDICTS (évalués dans cet ordre, doctrine du registre docs/20) :
  INSUFFISANT  n = mkFills+mkFb+mkTOut < N_MIN (30) : pas de conclusion possible
  DIVERGENCE   mkInv > 0 : l'invalidation ne devrait JAMAIS déclencher selon la
               mesure historique (0/469) -> soit les niveaux du plan différent
               de la doctrine _MK, soit un bug d'état : à audit AVANT tout reste
  CONFORME     test binomial exact bilateral de mkFills/n vs HYP_REF (93,82 %,
               mesurée sur le pool) avec p >= 0,05
  DÉRIVE_HAUT / DÉRIVE_BAS  p < 0,05 dans la direction correspondante
Le taux de SURVIE (trade réellement ouvert) = 1 - mkTOut/n est rapporté à part :
c'est lui qui nourrit la contrainte « moins de trades = moins d'edge cumulé ».

Sorties : JSON à côté du relevé + verdict console. Reproduction :
  python3 x501_mk_compteurs.py relevé.csv          # analyse d'un relevé
  python3 x501_mk_compteurs.py --demo              # démo auto-contenue (seed 501)
L'hypothèse de référence est re-déclarée ici pour être co-visionnée avec les
mesures : si la surface est re-mesurée, mettre à jour HYP_REF.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HYP_REF = 0.9382        # fill maker pur δ=2/TTL=2 mesuré sur pool P1 (PR vague4)
N_MIN = 30              # sous 30 tentatives, aucune conclusion (doctrine docs/28)
ALPHA = 0.05


def _log_pmf(k, n, p):
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) \
        + k * math.log(p) + (n - k) * math.log(1 - p)


def binom_test(k, n, p):
    """Test binomial exact (stdlib pure : log-gamma).
    Retourne (p_unilateral_du_cote_observé, p_bilateral_méthode_des_petites_probabilités)."""
    if n == 0:
        return 1.0, 1.0
    pmf = [math.exp(_log_pmf(i, n, p)) for i in range(n + 1)]
    pk = pmf[k]
    p2 = sum(x for x in pmf if x <= pk + 1e-12)
    if k / n <= p:
        pu = sum(pmf[: k + 1])
    else:
        pu = sum(pmf[k:])
    return min(1.0, pu), min(1.0, p2)


def analyser(releves, hyp_ref=HYP_REF, n_min=N_MIN):
    """releves : liste de dicts (clés du format ci-dessus). Retourne le verdict."""
    agg = {"mkFills": 0, "mkFb": 0, "mkTOut": 0, "mkInv": 0, "runs": len(releves)}
    fallback_on = []
    for r in releves:
        for k in ("mkFills", "mkFb", "mkTOut", "mkInv"):
            agg[k] += int(r.get(k, 0) or 0)
        fallback_on.append(int(r.get("fallback_on", 1) or 0))
    n = agg["mkFills"] + agg["mkFb"] + agg["mkTOut"]
    res = {"hyp_ref": hyp_ref, "n_min": n_min, "alpha": ALPHA, **agg,
           "n_tentatives": n, "fallback_mixed": len(set(fallback_on)) > 1}
    if n < n_min:
        res["verdict"] = "INSUFFISANT"
        res["note"] = (f"n={n} < {n_min} tentatives : aucune conclusion (agrègez "
                       f"plus de relevés — la règle JAMAIS de promotion sous N_MIN tient).")
        return res
    if agg["mkInv"] > 0:
        res["verdict"] = "DIVERGENCE"
        res["note"] = (f"mkInv={agg['mkInv']} > 0 : l'invalidation ne déclenche JAMAIS "
                       f"selon la mesure historique (0/469) — les niveaux du plan "
                       f"diffèrent de la doctrine _MK ou bug d'état : à AUDITER avant "
                       f"tout autre usage des compteurs.")
        return res
    k = agg["mkFills"]
    obs = k / n
    pu, p2 = binom_test(k, n, hyp_ref)
    res["fill_maker_pur"] = round(obs, 4)
    res["survie"] = round((agg["mkFills"] + agg["mkFb"]) / n, 4)
    res["p_uni"] = round(min(pu, 1.0), 4)
    res["p_bilateral"] = round(p2, 4)
    if p2 < ALPHA:
        res["verdict"] = "DÉRIVE_BAS" if obs < hyp_ref else "DÉRIVE_HAUT"
        res["note"] = (f"fill maker pur {obs*100:.1f} % vs {hyp_ref*100:.1f} % mesuré "
                       f"(p={p2:.4f}) : la dérive est significative — impact médian "
                       f"à re-calibrer avant promotion (règle des coûts : 1 pt de "
                       f"fill manquant ≈ les fallbacks désastreux −88,6 bps).")
    else:
        res["verdict"] = "CONFORME"
        res["note"] = (f"fill maker pur {obs*100:.1f} % compatible avec la mesure "
                       f"historique {hyp_ref*100:.1f} % (p={p2:.4f}).")
    return res


def lire_csv(p):
    import csv
    releves = []
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            releves.append({k.strip().lower(): v.strip() for k, v in row.items()})
    # normalisation des noms de colonnes
    out = []
    for r in releves:
        out.append({
            "date_iso": r.get("date_iso", ""),
            "symbole": r.get("symbole", r.get("sym", "")),
            "timeframe": r.get("timeframe", ""),
            "mkFills": r.get("mkfills", r.get("mkfills", 0)),
            "mkFb": r.get("mkfb", 0), "mkTOut": r.get("mktout", 0),
            "mkInv": r.get("mkinv", 0), "fallback_on": r.get("fallback_on", 1),
        })
    return out


def demo():
    # démo honnête : 3 relevés, 28 fills / 1 fallback / 1 abandon -> n=30 pile
    demo_releves = [
        {"date_iso": "2026-10-05", "symbole": "BTCUSDT", "timeframe": "H1",
         "mkFills": 10, "mkFb": 0, "mkTOut": 0, "mkInv": 0, "fallback_on": 1},
        {"date_iso": "2026-10-12", "symbole": "BTCUSDT", "timeframe": "H1",
         "mkFills": 11, "mkFb": 1, "mkTOut": 0, "mkInv": 0, "fallback_on": 1},
        {"date_iso": "2026-10-19", "symbole": "ETHUSDT", "timeframe": "H1",
         "mkFills": 7, "mkFb": 0, "mkTOut": 1, "mkInv": 0, "fallback_on": 1},
    ]
    print("DÉMO — 3 relevés papier (28 fills / 1 fallback / 1 abandon, n=30) :")
    r = analyser(demo_releves)
    print(json.dumps(r, indent=1, ensure_ascii=False))
    print("\nDÉMO — même chose avec mkInv=1 (divergence attendue) :")
    d2 = [dict(d) for d in demo_releves]
    d2[0]["mkInv"] = 1
    print(json.dumps(analyser(d2), indent=1, ensure_ascii=False))


def main():
    if "--demo" in sys.argv:
        demo()
        return
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    releves = lire_csv(sys.argv[1])
    if not releves:
        raise SystemExit("relevé vide")
    r = analyser(releves)
    print(json.dumps(r, indent=1, ensure_ascii=False))
    out = Path(sys.argv[1]).with_suffix(".verdict.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1, ensure_ascii=False)
    print(f"verdict -> {out}")


if __name__ == "__main__":
    main()
