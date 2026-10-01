# ORDRE DE BATAILLE x501 — ARMÉ

- Passe planificateur : **GO** (2026-10-01 06:08 UTC, il y a 0.0 h)
- Intégrité kScript : SHA256 **MATCH** + QA statique **PASS**
- Cadence : 0 3,9,15,21 * * * (UTC, hors fenêtres funding 00/08/16)

## Directions autorisées (signal-6 recalculé à froid)

| Symbole | LONG | SHORT | funding_z | liq_imb24 | OI 24h | ML danger short | Raisons de blocage |
|---|---|---|---|---|---|---|---|
| 1000PEPEUSDT | ✅ | ✅ | 0.623 | -0.088 | -1.37 % | — | — |
| ADAUSDT | ✅ | ✅ | 0.539 | -0.288 | 1.77 % | — | — |
| APTUSDT | ✅ | 🚫 | -1.531 | 0.719 | 1.54 % | — | liq_imb24=0.719>0.55 (capitulation long -> rebond); funding_z=-1.531<-1.5 (funding effondré) |
| AVAXUSDT | ✅ | ✅ | 0.761 | 0.537 | -2.95 % | — | — |
| BNBUSDT | ✅ | ✅ | -0.557 | -0.626 | -1.23 % | — | — |
| BTCUSDT | ✅ | ✅ | 0.297 | -0.379 | 2.8 % | — | — |
| DOGEUSDT | ✅ | ✅ | 0.95 | 0.107 | -2.38 % | — | — |
| ETHUSDT | ✅ | ✅ | 1.401 | -0.865 | 0.8 % | — | — |
| LINKUSDT | ✅ | 🚫 | 0.215 | 0.594 | 3.83 % | — | liq_imb24=0.594>0.55 (capitulation long -> rebond) |
| SOLUSDT | ✅ | ✅ | 1.617 | -0.638 | 2.04 % | — | — |
| SUIUSDT | ✅ | 🚫 | 0.439 | 0.618 | -2.61 % | — | liq_imb24=0.618>0.55 (capitulation long -> rebond) |
| XRPUSDT | ✅ | ✅ | -0.05 | 0.124 | 1.6 % | — | — |

**Résumé** : 12 longs autorisés, 9 shorts autorisés, 3 symboles partiellement bloqués, 0 écartés (features manquantes).

**ML advisory** : score danger-short du gate appris (leave-one-symbol-out, AUC 0,66-0,69 hors symboles vus) — absent ; non bloquant, promotion J+30.

## Contexte om_v29 (outils gratuits — advisory NON bloquant)

| Symbole | funding ann % | pos90 (0-1) | compress 30/90 (0-1) |
|---|---|---|---|
| 1000PEPEUSDT | 10.95 | 0.6729 | 0.6937 |
| ADAUSDT | 10.583 | 0.8867 | 0.6643 |
| APTUSDT | 10.95 | 0.8712 | 1.0 |
| AVAXUSDT | 10.95 | 0.9528 | 0.8383 |
| BNBUSDT | 0.507 | 0.8401 | 0.503 |
| BTCUSDT | 8.428 | 0.8927 | 0.4314 |
| DOGEUSDT | 9.535 | 0.7376 | 0.7225 |
| ETHUSDT | 7.251 | 0.9429 | 0.365 |
| LINKUSDT | 2.586 | 0.9397 | 0.6016 |
| SOLUSDT | 2.798 | 0.9234 | 0.538 |
| SUIUSDT | 10.95 | 0.8196 | 0.9447 |
| XRPUSDT | -2.304 | 0.7859 | 0.577 |

Verdicts v29 (walk-forward chrono global) : S1 carry funding **KILL** (train +29,6 / test -8,6 bps) ; S2 impulsion OI x prix **ADVISORY** (dispersion test 28,1 bps : flush +9,9 vs tendance -18,2) ; S3 structure **KILL** ; S4 régime vol DIAG. Aucun gate nouveau : la config certifiée 50/25/100 + maker reste l'autorité de blocage. Source : om_v27.db (âge 0.1 h).

*Généré automatiquement par x501_arm_v23.py — zéro intervention manuelle.*
