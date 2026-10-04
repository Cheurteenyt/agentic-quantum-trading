# LES FORCES MÉCANIQUES DE X.COM — le design Bonsai (05/10, sévère) + le filtre de l'agent

## LE REFRAME (la valeur de ce design)
**Les calls X ne sont pas des signaux, ce sont des ÉVÉNEMENTS DE LIQUIDITÉ.** Le caller est
positionné AVANT son tweet (sinon il n'a rien à gagner) — le call est un appât qui crée son
propre flux : les followers achètent APRÈS lui = l'exit liquidity. Trois horloges forcées :
- le CALLER : T+0 → T+15 min (le pump initial qu'il provoque)
- le FOLLOWER : T+15 → T+60 min (le retardataire qui chase)
- la SUPPRESSION : T+1h → T+24h (la réputation qui force l'effacement — capturable GRATUITEMENT
  par le diff des snapshots nocturnes : le post présent hier, absent aujourd'hui = délétré)

**La cohérence interne avec le registre** : le WR brut des calls = 44 % côté CHASE — et la loi
du labo dit fade bat chase → le côté FADE est le miroir à tester. Nos 44 % en chase sont un
INDICE pour le fade, pas contre lui.

## LE DESIGN FLAGSHIP : « La Fade du Follower »
Trigger = un call X publié · attendre T+15 min (fin du pump du caller) · condition
d'engagement (ratio > 5× la moyenne du caller — visible en réel dans le browser) ·
SHORT à T+15 · sortie T+60 min · pas de trade si l'engagement < 2× (le follower n'est pas forcé).
Prédiction Bonsai : WR 55-60 %, esp +1,5 %/trade (inventée, non mesurée — c'est le rôle du backtest).

## Le filtre de l'agent (avant pré-enregistrement)
1. **Pas de look-ahead** : l'entrée T+15 min est exécutable en réel (l'humain voit le call,
   attend, checke l'engagement dans le browser). Le conditionneur d'engagement est visible
   à T+15. PROPRE.
2. **La granularité** : les fenêtres 15/60 min exigent des prix 15m — klines 15m = 19 syms…
   MAIS le backfill listings du 03/10 = 338 syms × 15m, et les calls X se concentrent sur
   les listings. Le test 1h (close de l'heure du call → close de l'heure suivante) est
   possible pour les 592 calls dès maintenant.
3. **Les seuils (5×, 2×, +2 %, +1 %) sont de la théorie Bonsai** — c'est le BON type de
   pré-enregistrement (pas des données minées), à figer avant le run.
4. **Le prérequis honnête** : le backfill des rendements (le join klines) reste l'étape 1 —
   le fade se mesure sur les MÊMES 592 calls, côté inversé.
5. **Le tracker de suppression** : diff post_id entre snapshots nocturnes = une table
   x_deletions à zéro coût de collecte. Personne ne le fait. Le signal de réputation
   inversée est un conditionneur du score des callers, pas un signal directionnel.

## Ce qui manque encore
- L'engagement PAR CALL au moment T+15 (les metrics de x_posts sont le cumul au harvest —
  la vélocité T+15 nécessite un snapshot 15 min après le call : un job réactif à ajouter).
