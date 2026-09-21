# Aster public universe snapshot

Date: 2026-05-31

## Objectif

Elargir notre recherche Aster sans rester bloque sur toujours les memes paires.

Avant, beaucoup de runners exploraient surtout des presets fixes (`core`, `macro`, `equities`).
Ce module construit un snapshot public de l'univers Aster en utilisant uniquement des endpoints officiels read-only.

Module:

`backend/services/onchain/aster/aster_public_universe_snapshot.py`

Endpoint:

`/api/onchain/rpc/aster-public-universe-snapshot-preview`

Snapshot:

`backend/services/onchain/aster/aster_public_universe_snapshot_latest.json`

## Sources Aster validees

Le snapshot appelle les endpoints publics suivants:

- `/fapi/v3/exchangeInfo`
- `/fapi/v3/ticker/24hr` sans symbole
- `/fapi/v3/ticker/bookTicker` sans symbole
- `/fapi/v3/premiumIndex` sans symbole
- `/fapi/v3/fundingInfo` sans symbole

Ces endpoints ont ete probes en reel le 2026-05-31.

## Base URL operationnelle

Nos modules utilisent:

`https://fapi.asterdex.com`

La doc officielle montre aussi `https://fapi3.asterdex.com` dans certains exemples,
mais ce host retourne `403` depuis notre environnement. Pour les probes et les
runners, la base active doit donc rester `fapi.asterdex.com`.

## Resultat smoke reel

Resultat du snapshot `top_n=5`:

- `symbols_total`: `603`
- `symbols_trading`: `448`
- `symbols_usable_for_research`: `448`
- smoke direct `/ticker/bookTicker` sans symbole: `448` lignes
- smoke direct `/fundingInfo` sans symbole: `602` lignes
- smoke direct `/indexreferences?symbol=BTCUSDT`: `8` references

Top volume observe:

| Symbole | Quote volume 24h | Spread bps |
|---|---:|---:|
| ASTERUSDT | 344,472,575.44 | 1.35 |
| BTCUSDT | 293,063,318.26 | 0.01 |
| ETHUSDT | 168,293,870.11 | 0.05 |
| BNBUSDT | 162,636,232.49 | 0.41 |
| HYPEUSDT | 85,195,439.91 | 0.15 |

Top variation 24h observe:

| Symbole | Change 24h % | Quote volume 24h |
|---|---:|---:|
| PORTALUSDT | 43.819 | 598,069.89 |
| PLAYUSDT | 42.212 | 669,604.17 |
| AIAUSDT | 34.825 | 112,112.91 |
| TAKEUSDT | 29.926 | 16,182.43 |
| STGUSDT | 21.774 | 852,850.67 |

## Utilite pour nos backtests

Ce snapshot va servir a:

- detecter les paires Aster vraiment tradables au lieu de hardcoder la watchlist;
- alimenter un mode exploration plus puissant;
- classer les candidats par volume, spread, funding, premium mark/index;
- separer les actifs liquides des paires trop fines;
- eviter que les runners repetent toujours CRCLUSDT, INTCUSDT, MSFTUSDT ou LABUSDT sans explorer assez.

## Flags de prudence

Le snapshot marque chaque symbole avec `data_flags`:

- `not_trading`
- `low_24h_quote_volume`
- `wide_spread`
- `large_mark_index_premium`
- `high_funding_rate`
- `wide_funding_cap_floor`

Ces flags ne sont pas des signaux de trade. Ils servent uniquement a guider la recherche et la qualite de backtest.

## Garde-fous

- Aucun write DB.
- Aucun trade.
- Aucun wallet.
- Aucun endpoint signe.
- Aucun signal client.
- `write_snapshot=True` ecrit uniquement le JSON local de recherche Aster.
