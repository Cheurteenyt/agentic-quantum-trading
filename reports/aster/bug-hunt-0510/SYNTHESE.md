# LA CHASSE AUX BUGS — 05/10 (3 agents parallèles, lecture seule, territoires disjoints)

## Verdicts par agent
| Territoire | Critique | Mineur | Suspect |
|---|---|---|---|
| Chaîne d'évaluation (stacked_portfolio, p5, backtest_indicators) | **1** | 7 | 1 |
| Forward survivants (aster_survivors_forward, verdict janv 2027) | 0 | 2 | 1 |
| Collecteurs (the_machine, premium, fetch_deep_klines, health) | 0 | 3 | 2 |

## LE CRITIQUE — corr_months zero-fill (p5_frequency_test.py:362)
Le fill 0.0 des mois absents écrasait la corrélation vers 0 (corr réelle +1,00 lue +0,42).
**FIXÉ le 05/10** (intersection des mois communs) + RE-MESURE : vol_spike × cascade_majors
+0,043 → -0,055 ; × cascade_meme -0,650 inchangé (13 mois communs) — **les verdicts de
décorrélation tiennent**. Le bug aurait pu masquer une corrélation positive ; sur nos
données il n'a rien caché.

## Les 10 mineurs (la file de correction, priorisée)
1. funding_real_sum searchsorted "right" inclut le print déclencheur (+6-12 % de l'esp funding_sat)
2. gate ATR mesuré à atr[ei] (look-ahead d'1 barre) au lieu de atr[t]
3. months_all=12 codé dur (N/mois ×3-5 surestimés — display seul, espérance non touchée)
4. forward : la dernière barre de fenêtre inatteignable pour les sorties (auto-réparateur)
5. forward : captured_at en SECONDES vs ms (le piège d'unité classé)
6. backtest_indicators hold_h = h-1 (funding sous-compté d'1 h)
7. baseline blind : horizon décalé d'1 barre
8. stacked_portfolio sz = size (NameError latent si size_fn=None)
9. markdown ternaire : registre des liq malformé
10. aster_health STATE.write_text non gardé (contrat exit 0)

## Les 3 suspects (à trancher avant le 30/10)
- the_machine : max()/median() sans garde sur flux vide (crash latent du nocturne)
- aster_premium_collector : premium FAUSSE 0.0 si indexPrice absent → pollue les z-scores de crowding_composite (H-CROWD-1 du 30/10 !) — le collecteur est legacy (remplacé par markprice-ws), mais crowding lit premium_history
- time-stop forward : hold+1 barres d'exposition vs la convention T21 gelée (à aligner)

## Les contre-vérifications qui BLANCHIMENT
Le forward (flagship janvier) est PROPRE : pas de look-ahead (92/92 entrées à l'open t+1),
stop intrabar prioritaire, 8 bps sur notional, signe SHORT correct, watermark réel,
idempotence solide, replay_key sans collision. fetch_deep_klines (fix 03/10) validé champ
par champ. Et LA correction d'unité : premium_history est en POURCENT (-0,0448 = (mark/idx-1)×100),
pas en décimal — le piège premium_pct est inversé vs la mémoire ; l'évaluateur INV-N calcule
depuis mark/index bruts (immunisé), crowding_composite lit premium_pct brut (le suspect n°2
devient sa garde-fou à poser avant le 30/10).

## RÉSOLUTIONS (nuit du 05/10, avant le tir nocturne de 03:00)

**the_machine.py — les gardes flux-vide sont posées** (le SUSPECT n°2) : quatre points
d'agrégation (nanquantile des al_scores, max/median sur gated, sur meme, nanquantile surv)
refusaient une liste vide → le nocturne plantait avant son rapport. Fixé : « rapport abstenu »
propre si un flux est vide, calculs bit-identiques sinon.

**Le suspect n°3 (premiums 0.0) est un FAUX POSITIF — résolu par inspection** : les 4 999
lignes premium_pct = 0.0 ont mark == idx EXACT et des prix valides — des symboles à micro-prix
(DOGS 4,84e-05 : 2 616 lignes, DRAM 1 384, NEIRO 937) où la RÉSOLUTION de l'API rend
mark/idx identiques. Zéros de quantification, pas des données corrompues : zéro ligne avec
index_price <= 0. Rien à supprimer, rien à corriger dans les collecteurs (le garde
`if idx else 0.0` reste correct en défense). crowding_composite lit des zéros légitimes —
l'effet sur ses z-scores = la variance diluée des micro-prix, à garder en tête le 30/10.
