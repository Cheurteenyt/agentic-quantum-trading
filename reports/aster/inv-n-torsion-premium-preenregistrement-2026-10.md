# INV-N « LA TORSION DU PREMIUM » — PRÉ-ENREGISTREMENT (02/10, AVANT toute mesure)

Statut : **EXPERIMENTAL forward-only** — gouvernance docs/38, tag freeze-2026-10-02.
La donnée `premium_history` (mark vs index, WS 1 s, 54 432 lignes depuis 28/09) est
trop jeune pour un backtest — pré-enregistré MAINTENANT, jugé quand la fenêtre
atteint 30 j (~28/10). ADJACENCE : le funding (paiement périodique) est miné à fond
; le PREMIUM instantané (l'écart mark-index, le basis de la seconde) est une
variable distincte jamais testée. C'est la première tranche du composite CROWDING
de l'audit (§37/§61).

## La construction (jamais existée)

Par symbole : P_t = premium_pct lissé (moyenne 60 s) ; Z_t = z-score de P_t sur
fenêtre roulante 7 j (fit TRAIN au moment du gel). Événement = |Z_t| ≥ 3 (le
premium torsionné — un seul seuil).

## L'hypothèse falsifiable (pré-déclarée)

1. **Le premium revient** : après |Z| ≥ 3, le premium lui-même mean-revert vers
   sa moyenne en < 2 h (le déséquilibre de placement se dissipe).
2. **La torsion haussière extrême (Z ≥ +3) précède un repli du prix** sur 4-12 h
   (le surchauffage payé par les longs se corrige) — symétrique côté bas.

## PASS/FAIL écrits avant

- Reversion premium : moitié-vie médiane < 2 h en calibration ET validation, n ≥ 20.
- Impact prix : espérance nette du repli > étalon 12,2 bps en TRAIN ET VAL,
  contrôle inverse battu, n ≥ 20 par côté.
- FAIL : tout le reste — gravé, budget consommé, STOP.

## Garde-fous

1x, coûts 18 bps RT, BLOC STATS mensuel, verdict doctrine. Coordination : distinct
du tir OI H4/H5 (06-07/10) et d'INV-J (depth) — la variable ici = le premium
mark/index, jamais mesuré dans ce registre.
