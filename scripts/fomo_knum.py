#!/usr/bin/env python
r"""knum — la conversion UNIQUE des nombres abrégés de l'UI fomo.

Trois harvesteurs convertissaient chacun leurs nombres, avec des
angles morts différents (ronde 11, après le fix partiel #244) :

  - fomo_top_traders_miner.knum : `float(s.replace(",", ""))` —
    ValueError sur tout suffixe (« 1.2K ») : la quantité POS_RE abrégée
    mourait (perte silencieuse de la ligne).
  - fomo_holders_parser : ancres `[\d.,]+[KMB]?` MAJUSCULES-ONLY sans T —
    « 2.3T » cassait l'ancre de ligne entière (ligne perdue).
  - fomo_leaderboard_harvester (#244) : K/M/B — sans T, sans signe
    typographique, sans formats fr.

Inputs réels d'UI qui échappaient à tout ou partie des trois :
  1.234,5  (point de milliers fr — donnait 1.2345, erreur x1000)
  1 234,5  (espace/NBSP de milliers + virgule décimale)
  -1.2K    (moins typographique U+2212, pas le '-' ASCII)
  2.3T     (trillion, aucun suffixe T nulle part)

Ici : un seul contrat, testé. Retourne None si non parseable — JAMAIS
d'exception (une ligne UI étrange ne doit pas tuer un harvest).
"""
from __future__ import annotations

import re

# moins typographique + séparateurs d'espacement (NBSP, espace fine, etc.)
_NORMALIZE = {
    "\u2212": "-",   # minus sign
    "\u00a0": " ",   # no-break space
    "\u2009": " ",   # thin space
    "\u202f": " ",   # narrow no-break space
}

_NUM = re.compile(r"([+-]?[\d.,\s]*[\d.])\s*([KMBTkmbt]?)")


def knum(s):
    """'1,234.5' -> 1234.5 ; '1.2K' -> 1200.0 ; '2.3T' -> 2.3e12 ;
    '1.234,5' -> 1234.5 (fr) ; '\u22121.2K' -> -1200.0 ; non parseable -> None."""
    if not s:
        return None
    for bad, good in _NORMALIZE.items():
        s = s.replace(bad, good)
    s = s.strip()
    if not s:
        return None
    m = _NUM.fullmatch(s)
    if not m:
        return None
    num = m.group(1).replace(" ", "").strip(".,")
    if not num:
        return None
    if "," in num and "." in num:
        # le séparateur DÉCIMAL est le dernier des deux rencontrés
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")   # fr 1.234,5
        else:
            num = num.replace(",", "")                     # us 1,234.5
    elif "," in num:
        parts = num.split(",")
        if len(parts) > 1 and len(parts[-1]) in (1, 2):
            num = num.replace(",", ".")                    # 12,5 -> 12.5
        else:
            num = num.replace(",", "")                     # 1,234 -> 1234
    mult = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}.get(
        (m.group(2) or "").lower(), 1.0)
    try:
        return float(num) * mult
    except ValueError:
        return None
