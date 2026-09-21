# Carry intra-Aster — paires de perps qui se compensent

Genere : 2026-09-21T18:43:51Z UTC — 100 % Aster (contrainte utilisateur : aucun
autre exchange). Jambes : funding du DERNIER reglement, annualise.

Jambes courtes candidates : 6 | jambes longues : 4

| short (encaisse) | long (encaisse) | carry net ann. | correlation | lecture |
|---|---|---|---|---|
| PIEVERSEUSDT | SOLUSD1 | +80.8 % | 0.19 | pas un hedge |
| PIEVERSEUSDT | SOLUSDT | +81.8 % | 0.19 | pas un hedge |
| MEMEUSDT | SOLUSD1 | +105.6 % | 0.17 | pas un hedge |
| MEMEUSDT | SOLUSDT | +106.6 % | 0.16 | pas un hedge |
| MEMEUSDT | HYPEUSDT | +91.5 % | 0.15 | pas un hedge |
| INTCUSDT | SOLUSD1 | +49.8 % | 0.12 | pas un hedge |
| INTCUSDT | SOLUSDT | +50.8 % | 0.11 | pas un hedge |
| SKYAIUSDT | SOLUSDT | +44.3 % | 0.07 | pas un hedge |
| GUAUSDT | SOLUSDT | +62.9 % | 0.06 | pas un hedge |
| SKYAIUSDT | SOLUSD1 | +43.2 % | 0.05 | pas un hedge |
| GUAUSDT | SOLUSD1 | +61.8 % | 0.04 | pas un hedge |
| INTCUSDT | HYPEUSDT | +35.7 % | 0.04 | pas un hedge |
| PIEVERSEUSDT | HYPEUSDT | +66.7 % | 0.03 | pas un hedge |
| GUAUSDT | CLUSDT | +48.4 % | 0.02 | pas un hedge |
| GOOGLUSDT | SOLUSD1 | +42.7 % | 0.01 | pas un hedge |
| MEMEUSDT | CLUSDT | +92.1 % | 0.00 | pas un hedge |
| SKYAIUSDT | CLUSDT | +29.7 % | 0.00 | pas un hedge |
| GOOGLUSDT | CLUSDT | +29.2 % | 0.00 | pas un hedge |
| GOOGLUSDT | SOLUSDT | +43.8 % | 0.00 | pas un hedge |
| INTCUSDT | CLUSDT | +36.3 % | -0.00 | pas un hedge |
| GUAUSDT | HYPEUSDT | +47.8 % | -0.02 | pas un hedge |
| SKYAIUSDT | HYPEUSDT | +29.1 % | -0.04 | pas un hedge |
| PIEVERSEUSDT | CLUSDT | +67.3 % | -0.10 | pas un hedge |
| GOOGLUSDT | HYPEUSDT | +28.6 % | -0.12 | pas un hedge |

## Regle de lecture

Seules les paires 'quasi-neutres' (corr >= 0.70) se defendent comme
des carries. 'Correlation partielle' = du risque residuel reel.
'Pas un hedge' = deux paris opposes deguises en arbitrage.
Le funding varie a chaque reglement de 8 h ; les crises cassent les
correlations ; deux jambes = deux gestions de marge. Le carry range,
il ne conseille pas.
