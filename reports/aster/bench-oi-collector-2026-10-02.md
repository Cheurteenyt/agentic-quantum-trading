# Bench OI collector — 02/10/2026

**Méthode** : même endpoints Aster que `scripts/oi_collector.py`.  
**Ordre** : chemin ACTUEL mesuré d’abord, puis candidats, avec contrôle d’égalité OI.

## Setup

- 30 symboles (majors + memes Aster listés depth)
- Sandbox réseau public → `fapi.asterdex.com` / `www.asterdex.com/bapi`
- Pas de `klines.db` local : pure latence HTTP + parsing

## Résultats

| Chemin | n OK | Temps | Notes |
|---|---|---|---|
| **A — ACTUEL** seq fapi + `sleep 0.3` | 30/30 | **14.26 s** | logique `snapshot_pass` avant PR |
| **B — parallel 8 workers** | 30/30 | **0.51 s** | ×**27.8** vs A |
| **C — bulk bapi** | 645 sym | **0.66 s** | 1 HTTP, table `oi_history_bulk` |
| Depth REST 15 seq (réf.) | 15/15 | 2.51 s | engine WS déjà prod |
| Depth REST 15 parallel 8 | 15/15 | 0.47 s | ×5.3 vs seq |

## Correctness

- **A vs B** (même instant, 30 sym) : `max |ΔOI|/OI = 0`, median 0 → bit-identique.
- **Bulk vs fapi BTC** : `bulk / (fapi_oi × px) = 2.0000` (convention ×2 confirmée).
- Poids depth limit=500 ≈ **+10**, limit=1000 ≈ **+20** / appel.
- Parallel 30 OI : budget weight reste **&lt; 1800** (seuil health) sur le run de test.

## Décision PR

1. `--workers 8` par défaut pour la passe fapi (unités base `oi_history`).
2. `--workers 1` restaure **exactement** l’ancien seq+sleep (rollback comportemental).
3. Bulk inchangé (déjà optimal pour l’univers) ; cross-check majors inchangé.
4. Garde `weight >= 1500` → pause fin de minute (pattern `aster_blocktrades`).

## Ce que ce bench ne change pas

- Pas d’historique OI Aster (404 toujours).
- Depth prod = WS engine ; REST parallel n’est qu’une réf. de latence.
- Un seul écrivain SQLite par process (commit après la passe, pas pendant les GET).
