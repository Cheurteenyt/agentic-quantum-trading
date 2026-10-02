# AUDIT CODE the_machine.py — par le modèle local Bonsai, filtré par GLM (02/10)

Source : /tmp/bonsai_code_audit_out2.txt (sortie brute no-think, tronquée à 1800 tokens).
Le modèle local a produit 16 items ; le filtre GLM en retient 6 réels, 10 hallucinés.

## ✅ RÉELS (à considérer)

| # | Bonsai disait | Mon verdict |
|---|---|---|
| 1 | `write_text` sur mae_state.json n'est pas atomique — un disque plein ou un overlap laisserait un JSON corrompu | **RÉEL (MINEUR en pratique)** : le nocturne est single-timer donc pas d'overlap, mais l'écriture atomique (`tmp` + `os.replace`) est une bonne pratique pour un fichier d'état lu par d'autres process |
| 2 | `max(e["mae_adverse"] for e in meme)` lève ValueError si `meme` est vide | **RÉEL (défensif)** : 285 trades/an en pratique, mais si la DB est vide/migrée, le crash est brutal sans message |
| 3 | Idem pour `surv`, `spike`, `gated` — 4 `max()`/`median()` sans garde vide | **RÉEL (défensif)** : le pattern se répète 5× — un helper `_safe_max(seq)` éliminerait la classe entière |
| 4 | Les garde-fous comptables (gap_c, gap_p) ne se déclenchent pas si `mr` est vide | **RÉEL (défensif)** : si aucun trade, les gardes-fous passent silencieusement à 1.0/0.0 |

## ❌ HALLUCINÉS (Bonsai vérifie des états impossibles)

| # | Bonsai disait | Pourquoi c'est faux |
|---|---|---|
| 5-10 | Vérifier `CAPITAL == 0`, `max_dd is None`, `fees is None`, `funding is None`, `n_liq is None` | Ces valeurs viennent de `run_stack()` qui les **garantit toujours** (le simulateur du projet) — Bonsai vérifie des états qu'il ne peut pas atteindre |
| 11 | Le calcul de corrélation est "lourd" pour 1000+ trades | Le machine tourne 1×/nuit, pas en temps réel — la perf est non-pertinente |

## CE QUE BONSAI A MANQUÉ (mon audit complémentaire)

- `_K = 0.89` codé en dur sans commentaire justifiant le choix vs K=0.95 (à arbitrer au registre depuis le 28/09)
- Le heuristic d'unités timestamp `10**6 if t > 10**11 else 10**9` (le bug ts_ms du projet !) fonctionne mais sans commentaire explicatif
- `CORR_TILT` est derrière un flag CLI mais le registre le décrit comme le "module systémique" — le défaut OFF n'est pas justifié dans le code

## Verdict

Le modèle local trouve des vrais problèmes défensifs (4) et un vrai problème d'atomicité (1), mais passe 60 % de son budget sur des vérifications impossibles. **Signal/bruit ≈ 50 % en audit de code** (comparé à 20 % en génération d'hypothèses et 100 % en red-team). L'audit ne remplace pas une revue humaine mais fournit une liste de defensive-programming actionable.
