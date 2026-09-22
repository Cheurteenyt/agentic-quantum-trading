# Backtest — le funding extreme predit-il le prix ?
Genere : 2026-09-22T16:34:49Z UTC — percentile DANS l'historique de chaque symbole,
rendements forward depuis les klines 1h reelles, direction contrarian.
## Mise en garde affichee d'office
Les extremes de funding CLUSTERN dans le temps (plusieurs symboles au
meme moment) : les evenements ne sont pas independants, le N est gonfle.
Ce test decrit une tendance — il ne garantit rien et n'inclut pas les
couts d'execution (hormis le funding encaisse, credité a la jambe qui
collecte).
## Horizon +24h
- evenements : 616
- rendement contrarian moyen : +0.323 % (median +0.069 %)
- win rate contrarian : 51.1 %
- funding encaisse moyen : -0.0174 %
## Horizon +72h
- evenements : 564
- rendement contrarian moyen : +0.526 % (median +0.182 %)
- win rate contrarian : 51.6 %
- funding encaisse moyen : -0.0492 %
## Lecture honnete
Si le win rate et le mean restent dans le bruit (< 55 % et < 0.3 %),
l'hypothese est CLASSÉE dans les resultats nuls — comme les autres.
Si elle sort, elle devient un candidat a valider par la chaine
complete (gates, walk-forward, multiplicity). Pas avant.
