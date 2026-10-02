# Bench OI collector — 02/10/2026 (2 rounds)

**Regle** : mesurer le chemin ACTUEL d’abord, puis les candidats, avec egalite OI.

## Round 1 — sleep vs threads urllib vs bulk

| Chemin | n | Temps |
|---|---|---|
| A ACTUEL seq + sleep 0.3 | 30 | **14.26 s** |
| B urllib ThreadPool 8 | 30 | **0.51–0.70 s** |
| C bulk bapi | 645 | **0.36–0.66 s** |

A vs B : max \|dOI\|/OI = 0.

## Round 2 — le vrai goulot = TLS handshake, pas Aster

| Chemin | n | Temps | Notes |
|---|---|---|---|
| urllib seq **sans** sleep | 30 | 5.47 s | ~0.17 s/RTT × 30 |
| urllib ThreadPool 8 | 30 | 0.70 s | parallelise les handshakes |
| **http.client pool 8** | 30 | **0.040 s** | 1 TLS / worker, reuse |
| pool 8 | 100 | 2.11 s | weight_max 170 |
| pool 16 | 100 | **1.17 s** | weight_max 233 |
| bulk bapi | 645 | **0.36 s** | toujours le meilleur univers |

Correctness pool vs urllib (30) : max rel diff = **0**.

## Conclusion

1. Le sleep 0.3 s etait **surplus** (×28 deja avec threads).
2. Les threads urllib restent **10–15× plus lents** qu’un pool de connexions HTTPS.
3. Pour l’univers entier avec OI : **bulk bapi** gagne encore (1 appel).
4. Pour `oi_history` unites base fapi : **pool 8–16** = secondes meme a 100+ sym.
5. Depth prod reste WS ; REST depth pool 15 ≈ 0.46 s (reference seulement).

## Decision code

- `--workers 8` defaut = connection pool
- `--workers 1` = legacy seq+sleep (rollback)
- bulk inchange
- weight pause >= 1500 inchangee
