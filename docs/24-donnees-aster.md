# 24 — La couche de données Aster : l'état, les gaps, la feuille de route

> L'audit complet du 30/09 : ce qu'on collecte, comment, ce que l'API officielle
> offre, et le plan pour collecter mieux/vite/fiable. La source des docs API :
> github.com/asterdex/api-docs (V3 recommandée ; v1 et v3 = mêmes capacités
> market-data).

## Les limites du protocole (à graver)

- REQUEST_WEIGHT = **2 400/min par IP** ; 429 → backoff ; récidive → **ban 418
  (2 min → 3 jours)**. Nos pollings ≈ 40-50 poids/min = marge large, MAIS
  aucun collecteur permanent ne lit le header `X-MBX-USED-WEIGHT-1M` — le
  budget réel est inconnu.
- WS : ping serveur 5 min, pong attendu sous 15 min ; **connexion max 24 h**
  (reconnexion quotidienne obligatoire) ; **10 messages entrants/s par
  connexion** (limite dure) ; 200 streams max/connexion.
- `/fapi/v1/openInterest` : ABSENT des docs v1 ET v3 (endpoint non
  documenté, aucun stream WS OI) — le polling OI est inévitable ET fragile
  (un endpoint non documenté peut changer sans préavis).

## La matrice des gaps (ce qu'on poll → ce que le protocole offre)

| Donnée | Aujourd'hui | Stream natif | Gain | Priorité |
|---|---|---|---|---|
| Depth 500 niveaux × 15 sym | REST 30 s (2 880 req/j, ~43 k poids) | `@depth20@100ms` (20 niveaux seulement !) ou diff-depth + resync | temps réel + poids économisés MAIS 20 niveaux ≠ notre schéma 500 niveaux (wall_detector) → **moteur de carnet diff+snapshot** (stateful) | **P1** (le gros morceau) |
| Klines 1h/15m | nocturne 03:00 → **jusqu'à 24 h de retard** | `@kline_1h/15m` (250 ms, la bougie fermée est poussée) | la fraîcheur intra-journée pour le forward | **P2** |
| Premium/funding | REST 15 min ×~12 | `!markPrice@arr` @1s (TOUS les symboles, 1 msg/s) | 15 min → 1 s, 1 stream au lieu de 12 polls | **P3** (facile) |
| OI | REST 15 min ×2 collecteurs en doublon (même table !) | **aucun stream** (polling inévitable) | dédoublonner : garder oi_collector 15 min, tuer le nocturne dupliqué | **P4** (facile) |
| Liquidations | WS `!forceOrder@arr` ✅ déjà natif | — | déjà fait (le seul WS du parc) | — |
| aggTrades/prints | REST 15 min paginé | `@aggTrade` 100 ms | tape_1m en temps réel MAIS gros débit (100 ms) — à réserver aux majors | P5 |
| Le compteur de poids | aucun (429 subi) | header `X-MBX-USED-WEIGHT-1M` à lire partout | le budget réel devient visible, alerte avant le 429 | **P5** (transversal) |
| Funding ×3 chemins | refresh_cache + funding_history_collector + premium_history (3 univers, 2 versions) | consolidation | un seul besoin, une seule source | P6 |
| v1 vs v3 mélangés | depth/OI/aggTrades/premium en v1 ; klines/funding en v3 | v3 = « recommandée » (identique en market-data) | cohérence, préparation à la fin des clés v1 (03/2026) | P6 |

## Les pièges déjà vus (gravés)

- Les unités : depth_meta.ts en SECONDES, oi_history en ms, ts_ms ailleurs —
  tout join/sonde vérifie l'unité AVANT (le vert mensonger du 30/09).
- Le WS = connexion 24 h max : la reconnexion quotidienne est un événement
  NORMAL à planifier (le pattern backoff du liq_collector est le modèle).
- La veille S3 de la machine gèle TOUS les collecteurs (le trou de 4h49 du
  29/09) — l'inhibition est scopée au depth collector ; l'étendre = décision
  user (conso électrique).

## La feuille de route (l'ordre d'exécution)

1. **P4 + P5-transversal** (faciles, ce soir) : dédoublonner OI (tuer le
   nocturne dupliqué), le compteur de poids dans les 6 collecteurs REST
   (header lu, loggé, sondé par aster_health).
2. **P3 premium en `!markPrice@arr`** (1 stream, tous les symboles, 1 s) —
   remplace le poll 15 min, donne aussi la prédiction de funding native.
3. **P2 klines en WS** (les majors en `@kline_1h/15m` live → la fraîcheur
   intra-journée pour le forward ; le nocturne garde le backfill complet).
4. **P1 le moteur de carnet** (diff-depth + snapshot resync, stateful,
   reconstruction 500 niveaux) — le gros morceau, à faire APRÈS que P2-P4
   tournent, avec les tests de continuité de l'audit depth.
