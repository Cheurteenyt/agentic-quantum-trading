#!/usr/bin/env python3
"""N3 — la calibration de `_perm_loop` est MESURÉE, pas affirmée (audit
2026-10-08, action 3 du plan).

Avant ce fichier, le « 4,7 % » qui circulait dans les rapports venait
d'un script de l'auditeur, pas de `_perm_loop`. Le gate qui décide de
tout dans le dépôt n'avait **aucune mesure** de son propre taux de fausse
alerte.

Un gate trop laxiste produit des edges imaginaires. Un gate trop strict
produit du silence. **Les deux sont invisibles** sauf si on les mesure.

Le test séquentiel (N1b) change le nombre de tirages, donc la
distribution de la p-value. Mesurer UNE FOIS ne suffit pas : il faut
mesurer que l'arrêt précoce n'a pas mangé la validité.

## L'ÉCHELLE, et pourquoi elle est vérifiée

Le premier jet de ce fichier utilisait 300 événements et σ = 0,6 %.
Criterion d'acceptation du rapport : « puissance ≥ 90 % à +0,4 % ».
Il échouait — 2/50 détectés — et il avait raison d'échouer :

    SE(moyenne) = σ / sqrt(n) = 0,6 / sqrt(300) = 0,0346
    +0,4 %                     = 0,12 σ

**0,12 σ n'est pas detectable, par aucun test.** L'exiger, c'est demander
à l'oracle de mentir. Le critère du rapport était correct, mais mesuré
sur une paille : 300 événements contre ~27 000 dans le moteur réel.

Les constantes ci-dessous sont donc mesurées SUR LES RUNS RÉELS, et
`TestEchelleDuFixture` refuse de les laisser diverger. Un fixture qui
dérive de la production cesse de tester la production.
"""
from __future__ import annotations

import glob
import json
import sys
import time
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.research_runner import _perm_loop, sequential_perm_pvalue  # noqa: E402

H = 6
ALPHA = 0.05

# --- L'ÉCHELLE RÉELLE, mesurée sur les résumés de runs (voir le docstring) ---
# σ ≈ 1,56 % par événement 6h, et ~2 710 événements par symbole sur les 10
# symboles de univ10 → ~27 000 événements par étude.
N = 27105
SIGMA = 1.56
EV = 2710
COST = 0.28


def _cols(rng, mask, edge: float = 0.0):
    """cols minimal pour event_study. `edge` est ajouté à `ret` SUR les
    events seulement : edge NÉGATIF = crash = le short gagne."""
    ret = rng.normal(0, SIGMA, N)
    if edge:
        ret = ret.copy()
        ret[mask] += edge
    return {"ret_6": ret,
            "hi_6": np.abs(rng.normal(0, SIGMA / 2, N)),
            "lo_6": -np.abs(rng.normal(0, SIGMA / 2, N))}


def _une_marche(seed: int, edge: float = 0.0, n_perm: int = 429):
    """Une marche aléatoire indépendante → une p-value de `_perm_loop`."""
    rng = np.random.default_rng(seed)
    mask = np.zeros(N, dtype=bool)
    mask[rng.choice(N, EV, replace=False)] = True
    cols = _cols(rng, mask, edge=edge)
    mean_obs = float((-cols["ret_6"][mask] - COST).mean())
    p = _perm_loop([(cols, mask)], H, -1, COST, mean_obs=mean_obs,
                   n_perm=n_perm, seed=seed)
    return p


def _patterne(bits):
    """Un `exceed` déterministe, pour tester la forme sans event_study."""
    suite = list(bits)

    def exceed(_i):
        return suite.pop(0) if suite else False
    return exceed


class TestEchelleDuFixture(unittest.TestCase):
    """Le fixture doit ressembler à la production, ou il ne teste rien."""

    def test_sigma_et_n_ressemblent_aux_runs_reels(self):
        runs = glob.glob(str(ROOT / "research" / "runs" / "*" / "attempts"
                              / "*" / "summary_discovery.json"))
        sigmas, ns = [], []
        for f in runs:
            try:
                d = json.loads(Path(f).read_text("utf-8"))
            except Exception:
                continue
            for _sym, v in (d.get("per_symbol") or {}).items():
                if v.get("p10") is not None and v.get("p90") is not None \
                        and v.get("n"):
                    # p10..p90 couvre 2,563 σ
                    sigmas.append((v["p90"] - v["p10"]) / 2.563)
                    ns.append(v["n"])
        if not sigmas:
            self.skipTest("aucun run de découverte sur disque")
        sigma_reel = float(np.median(sigmas))
        n_reel = float(np.median(ns))
        # facteur 2 : la dispersion entre symboles est réelle et large
        self.assertLess(max(SIGMA, sigma_reel) / min(SIGMA, sigma_reel), 2.0,
                        f"σ du fixture = {SIGMA} %, σ réel = "
                        f"{sigma_reel:.2f} % : le fixture ne teste plus "
                        f"l'échelle de la production")
        self.assertLess(max(EV, n_reel) / min(EV, n_reel), 2.0,
                        f"n du fixture = {EV}, n réel = {n_reel:.0f}")

    def test_le_critere_du_repo_est_calibre_sur_le_bruit(self):
        """`min_mean = 0,02 %` doit être DU MÊME ORDRE que le seuil de
        détection (MDE, 90 % de puissance) — ni décoratif, ni impossible.

        Mesuré sur les runs réels (n POOLÉ, c'est ce que `_perm_loop`
        agrège) : MDE ≈ 0,024 %, `min_mean` = 0,02 %, soit **0,82×**.

        Donc une spec qui franchit `min_mean` a ~75 % de puissance, pas
        90 %. Ce n'est pas un défaut : `min_mean` est un PRÉ-FILTRE, et le
        gate qui décide est la p-value de permutation. Mais un critère
        placé 40× sous le bruit serait, lui, purement décoratif — et
        personne ne le remarquerait. La bande ci-dessous verrouille
        « calibré », pas « juste ».
        """
        n_poolle = self._n_poolle_reel()
        if n_poolle is None:
            self.skipTest("aucun run de découverte sur disque")
        mde = 2.33 * SIGMA / np.sqrt(n_poolle)
        ratio = 0.02 / mde
        self.assertGreater(
            ratio, 1 / 3,
            f"min_mean = 0,02 % est {ratio:.2f}× le MDE ({mde:.4f} % à "
            f"n={n_poolle:.0f}) : le critère de moyenne est décoratif, "
            f"3× sous le bruit")
        self.assertLess(
            ratio, 3.0,
            f"min_mean = 0,02 % est {ratio:.2f}× le MDE ({mde:.4f} %) : "
            f"le critère est inatteignable")

    @staticmethod
    def _n_poolle_reel():
        """Le `n` total que `_perm_loop` agrège réellement."""
        ns = []
        for f in glob.glob(str(ROOT / "research" / "runs" / "*" / "attempts"
                              / "*" / "summary_discovery.json")):
            try:
                d = json.loads(Path(f).read_text("utf-8"))
            except Exception:
                continue
            if isinstance(d.get("n"), int) and d["n"] > 0:
                ns.append(d["n"])
        return float(np.median(ns)) if ns else None


class TestFauxPositifs(unittest.TestCase):
    """Sous H0 (aucun edge), le gate doit laisser passer ~5 %, pas plus."""

    def test_fpr_sur_200_marches_independantes(self):
        """Critère d'acceptation N3 : P(p < 0,05) ≤ 8 %.

        8 % et non 5 % : c'est la marge d'erreur d'échantillonnage sur
        200 tirages (≈ ±2,5 % à 1,5 σ). Rejeter à 5 % pile rendrait le
        test instable d'un run à l'autre — un oracle qui clignote n'est
        pas un oracle.
        """
        n_marches = 200
        ps = [_une_marche(s) for s in range(n_marches)]
        fpr = sum(1 for p in ps if p < ALPHA) / n_marches
        self.assertLessEqual(
            fpr, 0.08,
            f"FPR = {fpr:.1%} sur {n_marches} marches sans edge "
            f"(seuil 8 %). Un gate trop laxiste fabrique des edges "
            f"imaginaires : c'est le défaut le plus coûteux du dépôt.")

    def test_aucune_p_value_nulle(self):
        """Une p-value de 0 est un artefact de comptage, pas une preuve.

        Le plancher est `1/(n_perm+1)` par construction.
        """
        for s in range(40):
            p = _une_marche(s, n_perm=99)
            with self.subTest(seed=s):
                self.assertGreater(p, 0.0,
                                   "p-value nulle : dépassements comptés "
                                   "sans être comptés")
                self.assertLessEqual(p, 1.0)


class TestPuissance(unittest.TestCase):
    """Avec un edge RÉEL, le gate doit le laisser passer."""

    def test_puissance_a_quatre_dixiemes_de_pourcent(self):
        """Critère d'acceptation N3 : puissance ≥ 90 % à ±0,4 %.

        Mesuré à l'échelle réelle : +0,4 % vaut 0,4/0,030 = 13 σ de la
        moyenne, donc la puissance est proche de 100 %. C'est la preuve
        que le moteur n'est pas sous-dimensionné — « la recherche ne
        produit rien » (N6) n'est donc pas un problème de statistiques.
        """
        n_marches = 100
        detectes = sum(1 for s in range(n_marches)
                       if _une_marche(9000 + s, edge=-0.4) < ALPHA)
        self.assertGreaterEqual(
            detectes / n_marches, 0.90,
            f"puissance = {detectes}/{n_marches} à −0,4 % : le gate rate un "
            f"edge franc")

    def test_un_edge_dans_le_MAUVAIS_sens_nest_pas_significatif(self):
        """La DIRECTION compte : +0,4 % ne doit rien prouver.

        Sans ce test, un gate qui se déclenche sur tout écart — dans un sens
        comme dans l'autre — passerait `test_puissance` tout en traitant
        une perte comme un edge. Ce test cloue ce point.
        """
        faux = [_une_marche(9000 + s, edge=0.4) for s in range(40)]
        significatifs = sum(1 for p in faux if p < ALPHA)
        self.assertLessEqual(significatifs, 2,
                             f"{significatifs}/40 edges à l'AVANTAGE DU LONG "
                             f"sortent significatifs : le gate détecte un "
                             f"écart, pas un edge")

    def test_un_edge_fort_atteint_le_plancher_bh(self):
        """Le plancher doit rester atteignable malgré l'arrêt précoce.

        C'est la raison d'arrêter au 10ᵉ dépassement et pas au 1ᵉ : un
        edge réel ne dépasse pas, il part une fois sur deux cents, donc il
        ne s'arrête jamais, donc il atteint `(0+1)/(n_perm+1)` — le seuil
        que le BH exige (N1, PR #198).
        """
        plancher = 1 / 430
        atteint = sum(1 for s in range(30)
                      if _une_marche(3000 + s, edge=-2.0) <= plancher + 1e-12)
        self.assertGreaterEqual(atteint, 27,
                                f"{atteint}/30 n'ont pas atteint le plancher "
                                f"{plancher:.5f} : le BH est inatteignable")


class TestArretPrecoce(unittest.TestCase):
    """N1b — l'arrêt précoce doit être un GAIN, pas une triche."""

    def test_le_nombre_de_tirages_baisse_sous_h0(self):
        """Sous H0, un tirage dépasse l'observé une fois sur deux, donc
        `h_stop=10` doit arrêter vers 20 tirages — pas 429.

        C'est le gain promis par N1b. Il doit être mesuré, pas espéré.
        """
        tirages = []
        for s in range(60):
            _, n = sequential_perm_pvalue(_patterne(
                [(i + s) % 2 == 0 for i in range(500)]),
                n_max=429, h_stop=10)
            tirages.append(n)
        moyenne = sum(tirages) / len(tirages)
        self.assertLess(moyenne, 40,
                        f"{moyenne:.0f} tirages en moyenne sous H0 au lieu "
                        f"de ≤ 40 : l'arrêt précoce ne sert à rien")
        self.assertGreater(moyenne, 10,
                           "arrêt trop brutal : on ne laisserait pas le "
                           "compteur de dépassements faire son travail")

    def test_sous_h0_l_arret_precoce_ne_abaisse_pas_artificialement(self):
        """Le même seed, arrêt précoce contre boucle complète.

        Ce qui ne doit PAS arriver : que l'arrêt rende systématiquement
        la p plus petite. La borne −0,35 autorise l'écart de bruit normal
        entre une p à 20 et une p à 429 tirages, et rien de plus.
        """
        ecarts = []
        for s in range(30):
            rng = np.random.default_rng(s)
            mask = np.zeros(N, dtype=bool)
            mask[rng.choice(N, EV, replace=False)] = True
            cols = _cols(rng, mask)
            mo = float((-cols["ret_6"][mask] - COST).mean())
            args = ([(cols, mask)], H, -1, COST)
            arret = _perm_loop(*args, mean_obs=mo, n_perm=99, seed=s,
                               h_stop=10)
            complet = _perm_loop(*args, mean_obs=mo, n_perm=99, seed=s,
                                 h_stop=0)
            ecarts.append(arret - complet)
        self.assertGreaterEqual(min(ecarts), -0.35,
                                "l'arrêt précoce abaisse la p-value sous H0 "
                                "plus que le bruit ne l'explique")


class TestSequentialPermPvalue(unittest.TestCase):
    """Le calcul pur, sans `event_study` — donc rapide et exact."""

    def test_arret_au_h_stopieme_depassement(self):
        # 3 dépassements au 6ᵉ tirage, h_stop=3 → arrêt net à 6
        p, n = sequential_perm_pvalue(_patterne([1, 0, 1, 0, 0, 1, 0]),
                                      n_max=99, h_stop=3)
        self.assertEqual(n, 6)
        self.assertAlmostEqual(p, 4 / 7)

    def test_aucun_depassement_prix_entier(self):
        p, n = sequential_perm_pvalue(_patterne([0] * 50), n_max=50,
                                      h_stop=10)
        self.assertEqual(n, 50)
        self.assertAlmostEqual(p, 1 / 51)

    def test_un_seul_depassement_ne_donne_pas_zero(self):
        """h_stop=1 : le 1ᵉ dépassement arrête tout de suite, p = 2/2 = 1.

        C'est la preuve que la formule `+1` du numérateur et du
        dénominateur n'est pas décorative : sans elle, p vaudrait 0 et le
        gate accepterait n'importe quoi au premier tirage.
        """
        p, n = sequential_perm_pvalue(_patterne([1]), n_max=99, h_stop=1)
        self.assertEqual(n, 1)
        self.assertAlmostEqual(p, 1.0)

    def test_un_seul_depassement_puis_bruit_prix_entier(self):
        """1 dépassement, `h_stop=2` jamais atteint → on va au bout.

        C'est le comportement IMPORTANT du test séquentiel : un exceedance
        isolé ne suffit pas à arrêter, donc on continue de tirer. C'est
        ce qui préserve la validité de la p-value.
        """
        p, n = sequential_perm_pvalue(_patterne([1]), n_max=99, h_stop=2)
        self.assertEqual(n, 99)
        self.assertAlmostEqual(p, 2 / 100)

    def test_h_stop_inaccessible_va_au_bout(self):
        p, n = sequential_perm_pvalue(_patterne([0, 1] * 10), n_max=20,
                                      h_stop=99)
        self.assertEqual(n, 20)
        self.assertAlmostEqual(p, 11 / 21)

    def test_n_max_non_bon(self):
        p, n = sequential_perm_pvalue(_patterne([1]), n_max=0, h_stop=10)
        self.assertEqual(n, 0)
        self.assertAlmostEqual(p, 1.0)

    def test_la_p_value_decroit_avec_les_depassements(self):
        """Plus de dépassements = p plus grande : le sens du gate."""
        ps = [sequential_perm_pvalue(_patterne([1] * k), n_max=20,
                                     h_stop=99)[0] for k in range(0, 6)]
        self.assertEqual(ps, sorted(ps))
        self.assertLess(ps[0], ps[-1])


class TestCoutMesure(unittest.TestCase):
    """N1b — le gain annoncé doit être mesuré sur le VRAI `_perm_loop`."""

    def test_l_arret_precoce_divise_le_temps(self):
        rng = np.random.default_rng(5)
        mask = np.zeros(N, dtype=bool)
        mask[rng.choice(N, EV, replace=False)] = True
        cols = _cols(rng, mask)
        mo = float((-cols["ret_6"][mask] - COST).mean())
        args = ([(cols, mask)], H, -1, COST)
        t0 = time.perf_counter()
        for _ in range(5):
            _perm_loop(*args, mean_obs=mo, n_perm=429, seed=1, h_stop=0)
        complet = time.perf_counter() - t0
        t0 = time.perf_counter()
        for _ in range(5):
            _perm_loop(*args, mean_obs=mo, n_perm=429, seed=1, h_stop=10)
        arret = time.perf_counter() - t0
        self.assertLess(arret, complet,
                        f"l'arrêt précoce n'a pas accéléré : {arret:.2f}s "
                        f"contre {complet:.2f}s")


if __name__ == "__main__":
    unittest.main()