# Carry intra-Aster — paires de perps qui se compensent

Genere : 2026-09-22T00:37:19Z UTC — 100 % Aster (contrainte utilisateur : aucun
autre exchange). Jambes : funding du DERNIER reglement, annualise.

Jambes courtes candidates : 6 | jambes longues : 4

| short (encaisse) | long (encaisse) | carry net ann. | correlation | spread pire jambe | lecture |
|---|---|---|---|---|---|---|
| CRCLUSDT | SOLUSDT | +45.7 % | 0.54 | 4.2 bps | correlation partielle |
| CRCLUSDT | SOLUSD1 | +44.6 % | 0.51 | 4.2 bps | correlation partielle |
| 1000PEPEUSDT | SOLUSDT | +78.5 % | 0.39 | 4.4 bps | pas un hedge |
| 1000PEPEUSDT | SOLUSD1 | +77.4 % | 0.38 | 4.4 bps | pas un hedge |
| DRAMUSDT | SOLUSD1 | +52.0 % | 0.22 | 4.8 bps | pas un hedge |
| DRAMUSDT | SOLUSDT | +53.1 % | 0.22 | 4.8 bps | pas un hedge |
| PIEVERSEUSDT | PLAYUSDT | +52.8 % | 0.19 | 3.8 bps | pas un hedge |
| PIEVERSEUSDT | SOLUSD1 | +50.9 % | 0.19 | 3.8 bps | pas un hedge |
| PIEVERSEUSDT | SOLUSDT | +51.9 % | 0.18 | 3.8 bps | pas un hedge |
| MEMEUSDT | SOLUSD1 | +63.0 % | 0.16 | 118.3 bps | pas un hedge / ILLIQUIDE |
| MEMEUSDT | SOLUSDT | +64.1 % | 0.15 | 118.3 bps | pas un hedge / ILLIQUIDE |
| CRCLUSDT | PLAYUSDT | +46.6 % | 0.11 | 4.2 bps | pas un hedge |
| SKYAIUSDT | SOLUSDT | +44.3 % | 0.07 | 13.8 bps | pas un hedge |
| SKYAIUSDT | PLAYUSDT | +45.1 % | 0.07 | 13.8 bps | pas un hedge |
| SKYAIUSDT | SOLUSD1 | +43.2 % | 0.05 | 13.8 bps | pas un hedge |
| MEMEUSDT | PLAYUSDT | +65.0 % | 0.02 | 118.3 bps | pas un hedge / ILLIQUIDE |
| MEMEUSDT | CLUSDT | +58.0 % | 0.02 | 118.3 bps | pas un hedge / ILLIQUIDE |
| DRAMUSDT | PLAYUSDT | +54.0 % | 0.00 | 4.8 bps | pas un hedge |
| SKYAIUSDT | CLUSDT | +38.2 % | 0.00 | 13.8 bps | pas un hedge |
| 1000PEPEUSDT | PLAYUSDT | +79.3 % | 0.00 | 4.4 bps | pas un hedge |
| 1000PEPEUSDT | CLUSDT | +72.4 % | -0.02 | 4.4 bps | pas un hedge |
| CRCLUSDT | CLUSDT | +39.6 % | -0.07 | 4.2 bps | pas un hedge |
| PIEVERSEUSDT | CLUSDT | +45.9 % | -0.10 | 3.8 bps | pas un hedge |
| DRAMUSDT | CLUSDT | +47.1 % | -0.18 | 4.8 bps | pas un hedge |

## Regle de lecture

Seules les paires 'quasi-neutres' (corr >= 0.70) se defendent comme
des carries. 'Correlation partielle' = du risque residuel reel.
'Pas un hedge' = deux paris opposes deguises en arbitrage.
Le funding varie a chaque reglement de 8 h ; les crises cassent les
correlations ; deux jambes = deux gestions de marge. Le carry range,
il ne conseille pas.
