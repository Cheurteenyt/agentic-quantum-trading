# Aster priority watchlist

Date: 2026-05-31

## Objectif

Produire une liste de symboles Aster a tester ensuite, sans rester bloque sur les memes actifs.

Module:

`backend/services/onchain/aster/research/watchlist_priority_builder.py`

Wrapper compat:

`backend/services/onchain/aster/aster_watchlist_priority_builder.py`

Endpoint:

`/api/onchain/rpc/aster-priority-watchlist-preview`

Snapshot:

`backend/services/onchain/aster/aster_priority_watchlist_latest.json`

## Methode

Le builder lit seulement des snapshots locaux:

- `aster_public_universe_snapshot_latest.json`;
- `aster_ws_symbol_quality_report_latest.json`;
- `aster_mark_index_replay_filter_latest.json`;
- `aster_research_consolidated_report_latest.json`.

Il ne fait aucun appel externe.

Score priorite:

- volume 24h;
- variation absolue 24h;
- spread;
- funding/premium;
- qualite WS;
- verdict mark/index;
- penalite si le symbole est deja surexploite;
- exclusion explicite des symboles focus.

## Snapshot actuel

Smoke du 2026-05-31:

- symbols_scored: `22`
- priority_count: `8`
- candidate_count: `0`
- blocked_count: `13`
- low_priority_count: `1`

Symboles recommandes:

1. `BTCUSDT`
2. `ASTERUSDT`
3. `HYPEUSDT`
4. `BNBUSDT`
5. `ETHUSDT`
6. `ETHUSD1`
7. `PLAYUSDT`
8. `SOLUSDT`

## Lecture importante

Cette watchlist n'est pas un signal de trade.

Elle sert a choisir quoi backtester ou monitorer ensuite:

- symboles liquides;
- spreads raisonnables;
- mouvements 24h interessants;
- flux WS acceptable si deja teste;
- moins de concentration sur LAB/INJ/CRCL/MSFT/INTC.

## Garde-fous

- Aucun appel externe.
- Aucun write DB.
- Aucun trade.
- Aucun wallet.
- Aucun signal client.
- `write_snapshot=True` ecrit seulement le JSON local de recherche.

## Prochaine etape

Utiliser cette watchlist pour lancer un runner discovery dedie:

- `BTCUSDT,ASTERUSDT,HYPEUSDT,BNBUSDT,ETHUSDT,ETHUSD1,PLAYUSDT,SOLUSDT`

Puis comparer ses resultats au cockpit principal avant d'ajouter ces symboles aux runners H24.
