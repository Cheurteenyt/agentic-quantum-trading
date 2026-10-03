# H-CROWD-1 — AMENDEMENTS PRÉ-TEST (fichier séparé, scellé à part)

Le fichier `crowding-composite.md` est SCELLÉ (sha256 gravé dans `scripts/crowding_composite.py`) et ne change plus.
Ces amendements ont été écrits le 02/10/2026 (commit 4b31e96), AVANT toute mesure et AVANT le tir du 30/10 ; ils étaient
d'abord ajoutés dans le fichier scellé, ce qui rompait le scellé (le script refusait de tourner : exit 2). Texte repris à l'identique.

## AMENDEMENTS PRE-TEST (02/10/2026 — red-team du modèle local Bonsai, AVANT toute mesure)

Le red-team (modèle local, medium thinking) a identifié 6 failles dont 2 actionnables avant le tir du 30/10 :

1. **Stratification par flux (paradoxe de Simpson)** : les 2 flux n'ont pas la même espérance intrinsèque et les états peuvent corréler avec la composition (plus de fades vol_spike en FRESH, plus de cascades gated en LATE). **AMENDEMENT : l'effet d'état se juge DANS chaque flux séparément (cascade gated d'un côté, vol_spike de l'autre) — jamais en pooled. Le critère C1-C4 s'applique par flux.**
2. **Incohérence temporelle du composite** : le funding (cycle 8h, lent) et l'OI/premium (rapides) mesurent des échelles de temps incompatibles — l'état LATE confond saturation historique et crowding instantané. **AMENDEMENT : le tir principal tourne avec le composite COMPLET, plus une variante de robustesse SANS la composante funding (4 composantes) — l'hypothèse ne survit que si les deux versions concordent.**

Les 4 autres failles du red-team (décalage temporel funding/OI en look-ahead, base-rate corrélé à la vol, les 2 suivantes tronquées) : documentées dans /tmp/hikari_redteam.txt, non actionnables avant le tir ou couvertes par les règles existantes (z-scores sur fenêtres passées = pas de look-ahead).

Ces amendements sont datés AVANT le 30/10 — le tir jugera la version amendée. Aucune autre modification ne sera acceptée après le tir.
