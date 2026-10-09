#!/usr/bin/env python
"""Alignement du taux funding sur l'index des barres — le helper blindé.

Trois scripts (signal_ladder, confluence_exact, backtest_indicators)
faisaient le même motif NU :

    rate = fh_sym.set_index("funding_time")["rate"].astype(float).sort_index()
    rate.index = pd.to_datetime(rate.index, unit="ms")
    aligned = rate.reindex(df.index, method="ffill", limit=8)

qui crash sur deux poisons RÉELS de la table funding_history :

  1. funding_time NULL -> NaT dans l'index -> `reindex(method="ffill")`
     exige un index monotone : ValueError (« limit argument for 'pad'
     method only well-defined if index and target are monotonic ») —
     reproduit en ronde 11 sur une seule ligne NULL.
  2. (symbol, funding_time) dupliqué -> « cannot reindex on an axis with
     duplicate labels » — reproduit. PR-166 documente des prints réels à
     +1..17 ms de l'heure pile : deux lignes tombent sur la même heure
     après troncature, les doublons ne sont pas hypothétiques.

Plus un poison silencieux (aucun crash, juste un signal mort) :

  3. l'unité ms est ASSUMÉE ; anti_liq.py:93 et stacked_portfolio.py:91
     normalisent des flux en SECONDES (x1000 à l'insert) — un flux en s
     donnait des dates 1970 : l'accel funding meurt en silence
     (diff(3) > 0 sur des NaN -> False partout).

Le helper applique le contrat existant à l'identique quand l'entrée est
saine : ffill avec limit=8 (le taux vaut 8 barres, périmé ensuite), et
déduplique premier-gagnant dans l'ordre d'arrivée — le même contrat que
FundingSeries.from_rows (funding_series.py, PR-166).
"""
from __future__ import annotations

import pandas as pd

# un epoch 2021+ vaut ~1.6e12 ms ou ~1.6e9 s : en dessous de 1e11, c'est
# des secondes (1e11 s = année 5138, aucun flux réel).
_S_MS_THRESHOLD = 10**11


def align_funding_rate(fh_sym: pd.DataFrame, target_index, limit: int = 8):
    """Série du taux funding alignée sur target_index (ffill, limit).

    fh_sym : lignes funding d'UN symbole avec colonnes `funding_time`
    (ms — s toléré, NULL et doublons admis) et `rate` (décimal).
    Retourne une pd.Series datetime-indexée alignée sur target_index :
    NaN hors couverture, comme l'ancien code quand l'entrée est saine.
    """
    g = fh_sym[["funding_time", "rate"]].copy()
    # NULL / non-numériques -> exclus : ils n'ont pas de place sur un axe
    # temporel ; l'ancien code les laissait casser la monotonie du reindex.
    g["funding_time"] = pd.to_numeric(g["funding_time"], errors="coerce")
    g = g.dropna(subset=["funding_time"])
    if (g["funding_time"] < _S_MS_THRESHOLD).all():
        g["funding_time"] = g["funding_time"] * 1000.0
    # doublons : premier-gagnant dans l'ordre d'arrivée (contrat PR-166)
    g = g.drop_duplicates(subset="funding_time", keep="first")
    rate = g.set_index("funding_time")["rate"].astype(float).sort_index()
    rate.index = pd.to_datetime(rate.index, unit="ms")
    return rate.reindex(target_index, method="ffill", limit=limit)
