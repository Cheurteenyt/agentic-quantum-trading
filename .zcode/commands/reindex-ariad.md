---
description: "Réindexer Ariad sur le workspace trading-agent (le graphe de code frais)"
---

Réindexe le graphe de code Ariad du projet : lance la commande suivante et rapporte le verdict (succès/échec + les warnings éventuels) :

`/usr/bin/node "$HOME/Projects/Ariad/v2/dist/cli/index.js" index --project trading-agent --root "$HOME/Projects/trading-agent"`

(~/Projects/trading-agent est un symlink vers le workspace monté "/run/media/cheurteen/Jeux SSD/trading-agent"). Si le graphe est utile à la suite, cite 2-3 faits du nouveau index (nœuds, fraîcheur). Une seule tentative, pas de retry.
