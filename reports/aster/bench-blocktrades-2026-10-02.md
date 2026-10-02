# Bench aster_blocktrades / aggTrades — 02/10/2026

**Methode** : chemin ACTUEL d’abord, puis pool + parallel, Aster live.

## Faits API

| Fait | Mesure |
|---|---|
| Weight / page `aggTrades?limit=1000` | **~20** (commentaire code disait ~5) |
| Budget fapi | 2400/min => **~120 pages/min** plafond theorique |
| RTT page typique | ~0.17–0.18 s |

## Incremental (6 majors × 15 min)

| Mode | Wall | Pages | Trades |
|---|---|---|---|
| CURRENT-like seq + sleep 0.2 page+sym | **2.24 s** | 6 | 1593 |
| pool + parallel 6 | **0.32 s** | 6 | 1597 |
| pool + parallel 3 | **0.49 s** | 6 | 1597 |

## Multi-pages BTC

| Fenetre | Pages | Trades | Persist nosleep | Persist sleep 0.2 |
|---|---|---|---|---|
| 6 h | 9 | 8209 | **2.74 s** | 4.36 s |
| 24 h | 35 | 34662 | **~24 s** (pause weight>=1500 ~14 s) | — |

## 6 majors × 1 h

| Mode | Wall | Trades | Pages |
|---|---|---|---|
| Seq persist nosleep | 3.36 s | 10257 | 14 |
| Parallel 6 | **1.43 s** | 10260 | 14 |

## Conclusions

1. Sleep 0.2 s est **secondaire** ; le plafond backfill = **weight 1500 pause**.
2. Parallel symboles = gros gain wall sur incremental (x7 sur 15 min x6).
3. Bootstrap multi-jours : parallel **borne a 3** pour ne pas bruler 2400/min.
4. Vrai saut suivant : **WS @aggTrade** (hors REST) — pas dans cette PR.

## Flags

- `--workers 4` defaut
- `--workers 1` = legacy seq + sleep 0.2
- `--pool` force pool meme en workers=1
- weight pause >=1500 inchangee
