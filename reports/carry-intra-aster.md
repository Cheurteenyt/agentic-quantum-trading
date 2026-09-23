# Carry intra-Aster — paires de perps qui se compensent

Genere : 2026-09-23T01:02:48Z UTC — 100 % Aster (contrainte utilisateur : aucun
autre exchange). Jambes : funding du DERNIER reglement, annualise.

Jambes courtes candidates : 6 | jambes longues : 4

| short (encaisse) | long (encaisse) | carry net ann. | correlation | spread pire jambe | lecture |
|---|---|---|---|---|---|---|
| CRCLUSDT | BTCUSDT | +32.0 % | 0.65 | 3.2 bps | correlation partielle |
| CRCLUSDT | SOLUSD1 | +44.6 % | 0.50 | 3.2 bps | correlation partielle |
| CRCLUSDT | PLAYUSDT | +46.6 % | 0.16 | 10.2 bps | pas un hedge |
| PIEVERSEUSDT | SOLUSD1 | +50.9 % | 0.16 | 3.4 bps | pas un hedge |
| DRAMUSDT | SOLUSD1 | +52.0 % | 0.15 | 4.7 bps | pas un hedge |
| PIEVERSEUSDT | PLAYUSDT | +52.8 % | 0.12 | 10.2 bps | pas un hedge |
| DRAMUSDT | BTCUSDT | +39.4 % | 0.12 | 4.7 bps | pas un hedge |
| SKYAIUSDT | BTCUSDT | +30.6 % | 0.10 | 10.0 bps | pas un hedge |
| SKYAIUSDT | SOLUSD1 | +43.2 % | 0.10 | 10.0 bps | pas un hedge |
| AMDUSDT | BTCUSDT | +28.0 % | 0.09 | 5.5 bps | pas un hedge |
| PIEVERSEUSDT | BTCUSDT | +38.3 % | 0.09 | 3.4 bps | pas un hedge |
| AMDUSDT | SOLUSD1 | +40.6 % | 0.08 | 5.5 bps | pas un hedge |
| MEMEUSDT | SOLUSD1 | +88.5 % | 0.07 | 278.9 bps | pas un hedge / ILLIQUIDE |
| SKYAIUSDT | PLAYUSDT | +45.1 % | 0.05 | 10.2 bps | pas un hedge |
| MEMEUSDT | CLUSDT | +83.5 % | 0.03 | 278.9 bps | pas un hedge / ILLIQUIDE |
| SKYAIUSDT | CLUSDT | +38.2 % | -0.00 | 10.0 bps | pas un hedge |
| MEMEUSDT | BTCUSDT | +75.9 % | -0.01 | 278.9 bps | pas un hedge / ILLIQUIDE |
| DRAMUSDT | PLAYUSDT | +54.0 % | -0.03 | 10.2 bps | pas un hedge |
| CRCLUSDT | CLUSDT | +39.6 % | -0.03 | 3.2 bps | pas un hedge |
| MEMEUSDT | PLAYUSDT | +90.4 % | -0.04 | 278.9 bps | pas un hedge / ILLIQUIDE |
| PIEVERSEUSDT | CLUSDT | +45.9 % | -0.10 | 3.4 bps | pas un hedge |
| DRAMUSDT | CLUSDT | +47.1 % | -0.10 | 4.7 bps | pas un hedge |
| AMDUSDT | CLUSDT | +35.7 % | -0.13 | 5.5 bps | pas un hedge |
| AMDUSDT | PLAYUSDT | +42.6 % | -0.20 | 10.2 bps | pas un hedge |

## Regle de lecture

Seules les paires 'quasi-neutres' (corr >= 0.70) se defendent comme
des carries. 'Correlation partielle' = du risque residuel reel.
'Pas un hedge' = deux paris opposes deguises en arbitrage.
Le funding varie a chaque reglement de 8 h ; les crises cassent les
correlations ; deux jambes = deux gestions de marge. Le carry range,
il ne conseille pas.
