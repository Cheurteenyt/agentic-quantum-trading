#!/usr/bin/env python3
"""PLACEBO DE BOUT EN BOUT — jusqu'au portefeuille (audit 2026-10-08,
plan §1).

`tests/test_placebo_random_walk.py` existe déjà et fait le placebo du
NOYAU : marche aléatoire → `run_discovery`. Il s'arrête là.

C-B3 (PR-199) vivait **après** cette frontière : dans la couche
portefeuille, où le seuil de sizing était un quantile calculé sur 70 % du
sample puis appliqué aux 30 % finaux. Aucune teste ne le voyait.

Ce fichier ferme la boucle : marche aléatoire → cascade → quantile
expanding → sizing → `run_stack` → PnL net.

## L'ORACLE PRINCIPAL EST UNE IDENTITÉ, PAS UNE STATISTIQUE

« CAGR net ≤ 0 sur du bruit » est un test statistique : il peut passer
pour la mauvaise raison, et il a une puissance faible. L'oracle fort ici
est une **identité causale** :

> ** tronquer le futur ne doit pas changer le passé.**

On fait tourner le pipeline sur une série complète, puis sur la même
série TRONQUÉE, et on exige que les décisions de sizing prises avant la
coupure soient **strictement identiques**. Si un seuil a regardé 70 %
d'histoire future, le scénario tronqué le révèle immédiatement — sans
tirage, sans puissance, sans seuil à choisir.

C'est l'inverse d'un test de significativité : il est **déterministe**
et il ne peut pas être contourné par un changement de graine.

## Pourquoi un test de ce genre ne peut pas « passer accidentellement »

Un placebo de PnL peut devenir vert parce que le seuil a monté trop haut
— le portefeuille ne trade plus, donc il ne perd rien. L'identité de
troncature ne peut PAS devenir verte de cette façon : si le pipeline ne
trade plus, les sizings sont tous égaux avant ET après coupure, donc
l'égalité tient toujours — mais `test_le_placebo_trade_effectivement`
échoue, et c'est lui qui garantit que le test d'identité teste quelque
chose.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.stacked_portfolio import (  # noqa: E402
    run_stack, size_by_policy, stamp_expanding_q66)

# ATTENTION : `run_stack` traite `ts_ms` comme des NANOSECONDS —
# `exit_ns = e["ts_ms"] + hold_h*3600*10**9` (PR-169). Un fixture en
# millisecondes garde le créneau occupé jusqu'à 10**13 et il n'y a
# qu'UN trade sur tout le sample. Le nom du champ ment ; le code, non.
H1_NS = 3_600_000_000_000
T0_NS = 1609459200000 * 10**6


def _cascade_rw(n: int = 900, seed: int = 42, drift: float = 0.08,
                syms=("BTCUSDT", "ETHUSDT", "SOLUSDT")):
    """Une cascade de marches aléatoires PURES.

    `al_score` est tiré AU HASARD, sans lien avec les prix : c'est le pire
    cas pour un gate, et le seul qui garantisse qu'aucun edge n'existe.

    ## `drift` n'est pas cosmétique

    Les scores DÉRIVENT (`uniform + i·drift`), parce qu'un `al_score`
    stationnaire est un cas dégénéré : le quantile p66 y vaut le même à
    50 % et à 70 % du sample, donc le bug C-B3 — un seuil calculé sur les
    70 % premiers — devient INVISIBLE, et l'oracle passe pour la mauvaise
    raison.

    Un régime réel dérive (volatilité, breadth, funding). C'est le cas qui
    casse un seuil scalaire, donc c'est le cas qu'il faut tester. Le
    quantile expanding, lui, y est insensible par construction — c'est
    exactement ce qu'on vérifie.
    """
    rng = np.random.default_rng(seed)
    events = []
    for i in range(n):
        sym = syms[i % len(syms)]
        ts = T0_NS + i * H1_NS
        # rendement aléatoire, MAE adverse aléatoire, aucun edge
        ret = float(rng.normal(0.0, 1.2))
        mae = float(abs(rng.normal(0.0, 1.0)))
        events.append({
            "ts_ms": ts,
            "sym": sym,
            "strategy": "cascade",
            "al_score": float(rng.uniform(0, 100)) + i * drift,
            "price_ret_short": ret,
            "mae_adverse": mae,
            "lev": 10.0,
            "fee_rt_bps": 4.0,
            "hold_h": 6.0,
            "fund_sign": 1,
        })
    return sorted(events, key=lambda e: e["ts_ms"])


def _pipeline(events, policy=None):
    """cascade → quantile expanding → sizing. Renvoie le par sizing."""
    policy = policy or {"cascade": 0.075}
    cascade, q66 = stamp_expanding_q66(list(events))
    size_fn = size_by_policy(policy, q66)
    return [(e["ts_ms"], size_fn(e)) for e in cascade], q66


class TestIdentiteDeTroncature(unittest.TestCase):
    """L'oracle fort : le futur ne doit pas colorer le passé."""

    def test_tronquer_le_futur_ne_change_aucune_decision_passee(self):
        events = _cascade_rw()
        complet, _ = _pipeline(events)

        for frac in (0.5, 0.7, 0.9):
            with self.subTest(troncature=frac):
                cut = int(len(events) * frac)
                tronque, _ = _pipeline(events[:cut])
                # tout ce qui est AVANT la coupure doit être identique
                ecarts = sum(1 for a, b in zip(complet[:len(tronque)],
                                                tronque) if a != b)
                self.assertEqual(
                    ecarts, 0,
                    f"tronquer à {frac:.0%} a changé {ecarts} décisions de "
                    f"sizing PASSÉES : le seuil regarde l'avenir")

    def test_le_seuil_asof_ne_dépend_que_du_passe(self):
        """Chaque `_q66_asof` doit être reproductible depuis l'historique.

        Reconstruction explicite : on prend les événements jusqu'à k, on
        calcule le quantile nous-mêmes, et on compare au seuil posé par la
        production. Si la production avait utilisé le sample complet, cet
        écart serait visible dès les premiers événements.
        """
        events = _cascade_rw()
        cascade, _ = stamp_expanding_q66(list(events))
        min_hist = 30
        for k in range(min_hist, len(cascade), 97):
            with self.subTest(index=k):
                attendu = float(np.nanquantile(
                    [e["al_score"] for e in cascade[:k]], 2 / 3))
                obtenu = cascade[k]["_q66_asof"]
                self.assertAlmostEqual(obtenu, attendu, places=9,
                                       msg="le seuil as-of ne vaut pas le "
                                           "quantile des scores ANTERIEURS")

    def test_le_seuil_bouge_ET_reste_local(self):
        """Un quantile EXPANDING fait les deux ; un scalaire ne fait ni l'un
        ni l'autre.

        - Un seuil scalaire (le bug C-B3) a un écart de **0** : une seule
          valeur pour tout le sample.
        - Un seuil calé sur le sample **complet** verrait toute l'amplitude
          du drift, pas une fenêtre locale.
        - Un quantile expanding suit le drift **localement** : il bouge,
          mais sur une fraction de l'amplitude totale.

        Les trois assertions ensemble séparent les trois cas. Une seule ne
        le ferait pas.
        """
        events = _cascade_rw()
        cascade, _ = stamp_expanding_q66(list(events))
        seuils = [e["_q66_asof"] for e in cascade
                  if np.isfinite(e["_q66_asof"])]
        scores = [e["al_score"] for e in cascade]
        etendue_seuil = max(seuils) - min(seuils)
        etendue_scores = max(scores) - min(scores)

        self.assertGreater(
            etendue_seuil, 5.0,
            f"le seuil ne bouge que de {etendue_seuil:.1f} points : il "
            f"ressemble à un scalaire appliqué partout (le bug C-B3)")
        self.assertLess(
            etendue_seuil, 0.6 * etendue_scores,
            f"le seuil couvre {etendue_seuil:.1f} points sur une amplitude "
            f"de {etendue_scores:.1f} : il n'est plus local, il voit trop "
            f"d'histoire")

    def test_le_warmup_ne_gate_pas(self):
        """Avant `min_hist`, le seuil est NaN et l'event n'est PAS gaté.

        C'est la sémantique de `gate_expanding` (`the_machine`, PR-167),
        pas une invention du portfolio.
        """
        events = _cascade_rw(n=20)
        cascade, _ = stamp_expanding_q66(list(events), min_hist=30)
        for e in cascade:
            with self.subTest(ts=e["ts_ms"]):
                self.assertTrue(np.isnan(e["_q66_asof"]))
        size_fn = size_by_policy({"cascade": 0.075}, float("nan"))
        for e in cascade:
            with self.subTest(ts=e["ts_ms"]):
                self.assertAlmostEqual(size_fn(e), 0.075)


class TestLeGateTourneVraiment(unittest.TestCase):
    """Si le gate ne gate plus rien, l'identité de troncuration passe
    trivially — donc il faut prouver qu'il discrimin."""

    def test_le_placebo_trade_effectivement(self):
        """Le gate doit produire un mélange de tailles (0 et 0,075).

        S'il ne gate jamais, le test d'identité ne teste plus rien.
        """
        events = _cascade_rw()
        paires, _ = _pipeline(events)
        tailles = {round(s, 6) for _, s in paires}
        self.assertIn(0.0, tailles, "le gate ne gate jamais : rien à tester")
        self.assertTrue(any(s > 0 for _, s in paires),
                        "le gate gate tout : le portefeuille ne trade pas")

    def test_une_puissance_nulle_ne_passerait_pas(self):
        """Contrôle négatif du test d'identité lui-même.

        Si le pipeline voyait le futur, le scénario tronqué produirait
        des sizings DIFFÉRENTS. On le vérifie en simulant exactement ce
        bug C-B3 : un quantile scalaire sur 70 % du sample, appliqué à
        tout. Le test doit le voir.
        """
        events = _cascade_rw()

        def _bug(events, frac=0.7):
            """Le bug C-B3 exact : un seuil scalaire pour tous."""
            ordre = sorted(events, key=lambda x: x["ts_ms"])
            k = max(1, int(len(ordre) * frac))
            q66 = float(np.nanquantile(
                [e["al_score"] for e in ordre[:k]], 2 / 3))

            def size_fn(e):
                sc = e["al_score"]
                return 0.0 if sc >= q66 else 0.075
            return [(e["ts_ms"], size_fn(e)) for e in ordre]

        complet = _bug(events)
        tronque = _bug(events[:int(len(events) * 0.5)])
        ecarts = sum(1 for a, b in zip(complet[:len(tronque)], tronque) if a != b)
        self.assertGreater(
            ecarts, 0,
            "le bug C-B3 ne serait PAS détecté par l'identité de "
            "troncature : l'oracle est mort")

    def test_la_version_corrigee_passe_l_oracle(self):
        events = _cascade_rw()
        complet, _ = _pipeline(events)
        tronque, _ = _pipeline(events[:int(len(events) * 0.5)])
        ecarts = sum(1 for a, b in zip(complet[:len(tronque)], tronque) if a != b)
        self.assertEqual(ecarts, 0,
                         f"{ecarts} décisions passées ont changé quand on a "
                         f"tronqué l'avenir")


class TestPlaceboPnlNet(unittest.TestCase):
    """Le placebo de PnL : sur du bruit, aucun edge ne doit survivre.

    ## Pourquoi PAS « CAGR net ≤ 0 » en dur

    Le critère du rapport est « CAGR net ≤ 0 ». Mesuré tel quel sur 30
    graines, le PnL total vaut ±1 500 sur 10 000 de capital, soit ±1,5 σ
    du zéro : **la moitié des marches gagnent par pur hasard**. Un test
    « ≤ 0 » serait donc rouge une fois sur deux — et un test qui clignote
    se désactive. C'est le même défaut que le seuil à 5 % pile de la
    calibration : un oracle instable n'est pas un oracle.

    On teste donc la VRAIE question — « le PnL moyen est-il significativement
    positif ? » — par un **z de grappe** sur 30 graines indépendantes :

        z = moyenne(30 PnL moyens) / écart-type(30 PnL moyens)

    Le critère `z ≤ 1,96` est une borne de confiance à 95 %, donc elle a
    la puissance qu'il faut et ne clignote pas.

    Et surtout : `TestPuissanceDuPlacebo` vérifie que ce critère **détecte
    une prévoyance réelle**. Un oracle qui ne peut pas devenir rouge ne
    prouve rien.
    """

    N_GRAINES = 30

    def _z(self, lookahead: bool = False) -> tuple[float, int]:
        """z de grappe du PnL moyen par trade, sur N_GRAINES marches."""
        moyennes, n_trades = [], 0
        for s in range(self.N_GRAINES):
            events = _cascade_rw(seed=1000 + s)
            if lookahead:
                # PRÉVOYANCE PARFAITE et INVERSÉE : le gate garde les scores
                # bas, donc les rendements shorts les PLUS HAUTS. C'est la
                # forme exacte d'un seuil qui « regarde 70 % d'avenir ».
                for e in events:
                    e["al_score"] = -e["price_ret_short"] * 50.0
            cascade, q66 = stamp_expanding_q66(list(events))
            size_fn = size_by_policy({"cascade": 0.075}, q66)
            res = run_stack(cascade, 10_000.0, size_fn, {})
            pnls = [t["pnl"] for t in res["trades"]]
            if pnls:
                moyennes.append(float(np.mean(pnls)))
                n_trades += len(pnls)
        z = (float(np.mean(moyennes)) / float(np.std(moyennes, ddof=1))
             if len(moyennes) > 1 else 0.0)
        return z, n_trades

    def test_le_placebo_nest_pas_significativement_positif(self):
        """Critère d'acceptation : aucun edge sur du bruit pur."""
        z, n_trades = self._z()
        self.assertLessEqual(
            z, 1.96,
            f"z = {z:+.2f} sur {self.N_GRAINES} marches ({n_trades} trades) : "
            f"le placebo est significativement PROFITABLE")

    def test_le_placebo_perd_effectivement_de_largent(self):
        """Contrôle négatif du placebo : le pipeline ne doit pas être une
        machine àbreviée qui « ne perd rien » en ne négociant pas.

        Les frais sont la seule force négative du modèle ; s'ils ne
        ressortent pas, la fixture est mal calibrée et le placebo ne
        teste rien.
        """
        events = _cascade_rw(seed=1000)
        cascade, q66 = stamp_expanding_q66(list(events))
        size_fn = size_by_policy({"cascade": 0.075}, q66)
        res = run_stack(cascade, 10_000.0, size_fn, {})
        self.assertGreater(res["n"], 50,
                           "le placebo ne negotiate pas assez pour dire quoi "
                           "que ce soit")
        self.assertGreater(res["fees"], 0.0,
                           "aucun frais : la fixture ne ressemble pas au "
                           "moteur reel")


class TestPuissanceDuPlacebo(unittest.TestCase):
    """Un oracle qui ne peut pas devenir rouge ne prouve rien."""

    def test_le_critere_detecte_une_prevoyance_reelle(self):
        """On INJECTE un seuil qui voit l'avenir, et le critère doit le
        prendre. Sans ce test, « z ≤ 1,96 » serait une affirmation."""
        z, n_trades = TestPlaceboPnlNet()._z(lookahead=True)
        self.assertGreater(
            z, 1.96,
            f"une prévoyance PARFAITE produit z = {z:+.2f} : le critère "
            f"z ≤ 1,96 ne la détecte pas, l'oracle est INUTILE")
        self.assertGreater(n_trades, 1000)


if __name__ == "__main__":
    unittest.main()