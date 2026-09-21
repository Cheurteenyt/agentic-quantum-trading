"""Moteur de backtest v2 — la couche qui rend le mensonge structurellement impossible.

Ce package n'implemente PAS de strategie. Il implemente les garde-fous qui
manquaient au legacy Aster (voir docs/03-methodology.md et docs/06-data.md) :

    store.py   le schema : identite obligatoire, perdants persistes, realise/latent
               separes, blobs isoles, schema versionne, denominateur conserve
    gates.py   les criteres de rejet automatique + les benchmarks obligatoires

Ordre de construction volontaire : les gates AVANT le moteur. Un moteur qui
produit des resultats avant que les gates existent produit des mensonges.
"""

SCHEMA_VERSION = "v2.0.0"

__all__ = ["SCHEMA_VERSION"]
