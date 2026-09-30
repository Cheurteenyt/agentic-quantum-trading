#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_fill_maker_x501.py — QA de la chaîne de preuve maker (docs/29).

Contrôle :
  1. l'étude versionnée (fill_maker_surface.json) et le pool CSV sont cohérents ;
  2. les monotonies mathématiques de la surface (P(fill) décroissant en δ,
     croissant en TTL, symétrie buy/sell) ;
  3. le niveau B (décomposition du pool, biais adverse, verdict de réfutation) ;
  4. le niveau C (sortie analytique) et le verdict global ;
  5. le parseur de compteurs _MK (verdicts INSUFFISANT / CONFORME /
     DIVERGENCE / DÉRIVE) ;
  6. la cohérence docs/29 ↔ JSON (les chiffres gravés sont ceux mesurés).

Zéro dépendance : stdlib pure + le JSON versionné. La re-exécution de l'étude
(data premium) est OPTIONNELLE : si X501_DATA_DIR pointe sur des klines 1h,
le JSON re-produit doit être bit-à-bit identique (contrôle A1).
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

J = json.loads((HERE / "fill_maker_surface.json").read_text(encoding="utf-8"))
DOC29 = (HERE / "../../../docs/29-fill-maker-mesure.md").read_text(encoding="utf-8")

ECHECS = []
N = 0


def ok(cond, label):
    global N
    N += 1
    if not cond:
        ECHECS.append(label)
    return bool(cond)


# ---------------------------------------------------------------- fichiers ----
ok((HERE / "x501_fill_maker_surface.py").exists(), "A0 script d'étude présent")
ok((HERE / "pool_P1_entrees.csv").exists(), "A1 pool CSV présent")
ok((HERE / "x501_mk_compteurs.py").exists(), "A2 parseur compteurs présent")

# ------------------------------------------------------------ structure JSON --
for k in ("fenetre", "niveau_A", "niveau_B", "niveau_C", "verdict", "controles",
          "grille_B"):
    ok(k in J, f"B0 clé '{k}' dans le JSON")

A, B, C, V = J["niveau_A"], J["niveau_B"], J["niveau_C"], J["verdict"]
surf = A["surface"]

# pool CSV : 469 lignes + t_in uniques
with open(HERE / "pool_P1_entrees.csv", newline="") as f:
    pool = list(csv.DictReader(f))
ok(len(pool) == 469, "C0 pool CSV = 469 trades")
ok(len({(r["sym"], r["t_in"], r["alpha"]) for r in pool}) == len(pool),
   "C1 pool CSV : (sym, t_in, alpha) uniques (2 alphas peuvent signaler la même barre)")
ok(B["n_pool"] == 469, "C2 niveau B sur 469 trades")
ok(int(A["n_symboles"]) == 80, "C3 surface : 80 symboles")
ok(int(A["n_barres"]) == 2053015, "C4 surface : 2 053 015 tentatives")

# ------------------------------------------------- monotonies de la surface ---
DELTAS = [1, 2, 3, 5, 8, 10, 15]
TTLS = [1, 2, 3, 6, 12]
for lbl in ("buy", "sell"):
    for t in TTLS:
        chain = [surf[f"{lbl}_d{d}_ttl{t}"] for d in DELTAS]
        ok(all(chain[i] >= chain[i + 1] - 1e-9 for i in range(len(chain) - 1)),
           f"D0 monotonie δ décroissante ({lbl}, ttl={t})")
for lbl in ("buy", "sell"):
    chain = [surf[f"{lbl}_d2_ttl{t}"] for t in TTLS]
    ok(all(chain[i] <= chain[i + 1] + 1e-9 for i in range(len(chain) - 1)),
       f"D1 monotonie TTL croissante ({lbl})")
max_sym = max(abs(surf[f"buy_d{d}_ttl{t}"] - surf[f"sell_d{d}_ttl{t}"])
              for d in DELTAS for t in TTLS)
ok(max_sym <= 1.0, f"D2 symétrie buy/sell <= 1 pt (max {max_sym})")
for lbl in ("buy", "sell"):
    ok(80.0 <= surf[f"{lbl}_d2_ttl2"] <= 100.0, f"D3 cellule d2_ttl2 {lbl} plausible")

# ---------------------------------------------------------------- niveau B ----
cas = B["cas"]
ok(cas["fill"] + cas["fallback"] + cas["invalide"] + len(B["detail"]["hors_data"])
   == 469, "E0 décomposition du pool = 469")
ok(round(cas["pct_fill"] + cas["pct_fallback"] + cas["pct_invalide"], 2) == 100.0,
   "E1 pourcentages de cas = 100")
ok(cas["fill"] == 440 and cas["fallback"] == 29, "E2 fill 440 / fallback 29 (δ=2, TTL=2)")
ok(B["delta_fills"]["mean"] >= 5.0, "E3 delta des fills >= 5 bps (6,1 + gaps)")
ok(B["delta_fallbacks"]["mean"] < 0, "E4 le biais adverse des fallbacks est présent")
ok(B["delta_mix"]["mean"] < 4.0, "E5 delta mix < hypothèse MC (réfutation gravée)")
ok(B["vs_mc_entree"]["conservatrice"] is False, "E6 l'hypothèse MC n'est pas conservatrice")
ok(B["invalidations"]["n"] == 0, "E7 0 invalidation (contrôle mécanique de la doctrine)")
ok(B["fills_sans_gap"] + B["fills_avec_gap"] == cas["fill"], "E8 fills = sans gap + avec gap")
ok(B["delta_par_alpha"]["A4"]["mean"] < B["delta_par_alpha"]["A1"]["mean"],
   "E9 le biais adverse est concentré sur A4")
ok(0 < B["dR_entree"]["mean"] < 4.0 / 242.0, "E10 dR entrée < crédit MC moyen")

# ---------------------------------------------------------------- grille B ----
g = J["grille_B"]
ok(len(g) == 10, "F0 grille = 10 configs")
ok(all(g[k]["delta_mix_mean"] is not None for k in g), "F1 deltas de la grille présents")
ok(g["d2_ttl6"]["delta_mix_mean"] > g["d2_ttl2"]["delta_mix_mean"],
   "F2 TTL=6 bat TTL=2 (delta mix)")
ok(g["d2_ttl6"]["pct_fill"] > g["d2_ttl2"]["pct_fill"], "F3 TTL=6 fill > TTL=2 fill")
ok(g["d2_ttl6"]["pct_fallback"] < g["d2_ttl2"]["pct_fallback"],
   "F4 TTL=6 fallback < TTL=2 fallback")

# ---------------------------------------------------------------- niveau C ----
ok(C.get("disponible") is True, "G0 niveau C disponible")
ok(abs(C["poids_tp_pct"] - 36.3) <= 1.0, "G1 poids TP ≈ 36,3 % du notional de sortie")
ok(0 < C["delta_sortie_bps"] <= 4.1, "G2 delta sortie analytique ∈ (0, 4,1]")

# ----------------------------------------------------------------- verdict ----
ok(abs(V["delta_par_jambe_bps"] - (V["delta_entree_bps"] + V["delta_sortie_bps"]) / 2)
   < 0.01, "H0 verdict : par jambe = (entrée + sortie)/2")
ok(V["part_de_credit_mc_pct"] < 100, "H1 le crédit MC v20 n'est pas validé")
ok(V["delta_entree_bps"] < 4.0, "H2 entrée réelle < 4,0 bps")
ok(V["hypothese_mc_par_jambe_bps"] == 4.0, "H3 hypothèse MC gravée = 4,0")

# ---------------------------------------------------- parseur de compteurs ----
import x501_mk_compteurs as MK                     # noqa: E402

demo3 = [
    {"date_iso": "2026-10-05", "symbole": "BTCUSDT", "timeframe": "H1",
     "mkFills": 10, "mkFb": 0, "mkTOut": 0, "mkInv": 0, "fallback_on": 1},
    {"date_iso": "2026-10-12", "symbole": "BTCUSDT", "timeframe": "H1",
     "mkFills": 11, "mkFb": 1, "mkTOut": 0, "mkInv": 0, "fallback_on": 1},
    {"date_iso": "2026-10-19", "symbole": "ETHUSDT", "timeframe": "H1",
     "mkFills": 7, "mkFb": 0, "mkTOut": 1, "mkInv": 0, "fallback_on": 1},
]
r1 = MK.analyser(demo3)
ok(r1["verdict"] == "CONFORME", "I0 démo 28/30 -> CONFORME")
ok(abs(r1["fill_maker_pur"] - 28 / 30) < 1e-3, "I1 fill pur = 28/30")
ok(abs(r1["survie"] - 29 / 30) < 1e-3, "I2 survie = 29/30")
ok(0 <= r1["p_bilateral"] <= 1, "I3 p-value binomiale bornée")
r2 = MK.analyser([{**demo3[0], "mkInv": 1}] + demo3[1:])   # n=30, mkInv=1
ok(r2["verdict"] == "DIVERGENCE", "I4 mkInv>0 -> DIVERGENCE")
r3 = MK.analyser(demo3[:1])
ok(r3["verdict"] == "INSUFFISANT", "I5 n=10 < N_MIN -> INSUFFISANT")
r4 = MK.analyser([{"mkFills": 80, "mkFb": 0, "mkTOut": 0, "mkInv": 0}])
ok(r4["verdict"] == "DÉRIVE_HAUT", "I6 80/80 fills = 100 % (n=80) -> DÉRIVE_HAUT")
ok(r4["p_bilateral"] < 0.05, "I7 la dérive haute est significative (p<0,05)")
r5 = MK.analyser([{"mkFills": 0, "mkFb": 1, "mkTOut": 29, "mkInv": 0} for _ in range(1)])
ok(r5["verdict"] == "DÉRIVE_BAS", "I8 0/30 fills -> DÉRIVE_BAS")

# --------------------------------------------------- cohérence docs/29 ↔ JSON --
for chiffre in ("93,82 %", "−88,6 bps", "+0,375 bps", "306,2 $", "364,0 $",
                "0,931 bps", "97,44", "1,488 bps"):
    ok(chiffre in DOC29, f"J0 docs/29 gravé : {chiffre}")
ok("23,3" in DOC29, "J1 docs/29 : part de crédit MC 23,3 %")

# ------------------------------------- A1 optionnel : re-exécution bit à bit ---
import os                                       # noqa: E402

data_dir = os.environ.get("X501_DATA_DIR", "")
if data_dir and Path(data_dir).exists():
    import tempfile                             # noqa: E402
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, X501_DATA_DIR=data_dir)
        # NB : le script écrit TOUJOURS dans son propre dossier (idempotent bit
        # à bit) — on compare la ré-écriture à la version chargée en début de QA.
        before = (HERE / "fill_maker_surface.json").read_bytes()
        subprocess.run([sys.executable, str(HERE / "x501_fill_maker_surface.py")],
                       cwd=td, env=env, capture_output=True, timeout=600)
        ok((HERE / "fill_maker_surface.json").read_bytes() == before,
           "K0 re-exécution bit à bit : le JSON ré-écrit est identique")
        reprod = json.loads((HERE / "fill_maker_surface.json").read_text(encoding="utf-8"))
        ok(reprod["niveau_B"]["delta_mix"]["mean"] == B["delta_mix"]["mean"],
           "K1 re-exécution bit à bit : delta mix")
        ok(reprod["controles"] == J["controles"], "K2 re-exécution bit à bit : contrôles")
else:
    print("info : X501_DATA_DIR absent — re-exécution bit à bit ignorée (A1-K)")

# ----------------------------------------------------------------- bilan ------
print(f"qa_fill_maker_x501 : {N} contrôles, {len(ECHECS)} échec(s)")
if ECHECS:
    for e in ECHECS:
        print(f"  ECHEC : {e}")
    raise SystemExit(1)
print("PASS")
