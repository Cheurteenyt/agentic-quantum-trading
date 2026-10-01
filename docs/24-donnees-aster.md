# 24 — La couche de données Aster : l'état, les gaps, la feuille de route

> **domain: ASTER** · index data : [`data/README.md`](data/README.md) · reports : `reports/aster/`
>
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
| Depth 500 niveaux × 15 sym | ~~REST 30 s~~ | `@depth@500ms` | ✅ **P1 FAIT** aster_depth_engine 24/7 | **P1** ✅ |
| Klines 1h/15m | nocturne → retard jusqu'à 24 h | `@kline_1h/15m` | fraîcheur forward | **P2** |
| Premium/funding | REST 15 min | `!markPrice@arr` | ✅ P3 FAIT aster_markprice_ws | **P3** ✅ |
| OI | REST 15 min (doublon nocturne retiré) | aucun stream | ✅ P4 FAIT | **P4** ✅ |
| Liquidations | WS `!forceOrder@arr` | — | déjà natif | — |
| Compteur poids | header lu | `X-MBX-USED-WEIGHT-1M` | ✅ P5 FAIT aster_rate + health | **P5** ✅ |
| Funding bulk / univers | multi-chemins | bapi bulk | ✅ P6 FAIT | **P6** ✅ |

## Pièges gravés

- Unités ts : secondes vs ms — vérifier AVANT tout join
- WS max 24 h : reconnexion quotidienne = normal
- Veille S3 machine : inhibition scopée depth (pas tout geler sans décision)

## API interne UI (bapi) — P6

- `ticker/pair` : 642 symboles OI bulk → `oi_history_bulk` (notional USDT ×2, table dédiée)
- `real-time-funding-rate` : meta interval/cap → `funding_meta`
- Header poids ABSENT sur bapi (hors budget fapi 2400)

Détail historique des acceptations T+10/T+20 depth : commit d'origine 30/09.
