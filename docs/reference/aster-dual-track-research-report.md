# Aster dual-track research report

Date: 2026-05-31

## Objectif

Ne pas abandonner les anciens backtests tout en continuant a explorer de nouveaux actifs.

Module:

`backend/services/onchain/aster/research/dual_track_research_report.py`

Wrapper compat:

`backend/services/onchain/aster/aster_dual_track_research_report.py`

Endpoint:

`/api/onchain/rpc/aster-dual-track-research-report-preview`

Snapshot:

`backend/services/onchain/aster/aster_dual_track_research_report_latest.json`

## Methode

Le rapport lit seulement deux snapshots locaux:

- `aster_research_consolidated_report_latest.json`;
- `aster_priority_watchlist_latest.json`.

Il separe le travail en trois pistes:

- `exploitation_track`: champions historiques deja observes en backtest/paper.
- `exploration_track`: nouveaux symboles issus de la watchlist priorisee.
- `preserve_history_track`: symboles qu'on ne doit pas oublier, meme si on ne les relance pas a chaque cycle.

## Pourquoi c'est important

Le projet avait deux risques opposes:

- rester bloque sur les memes actifs (`LAB`, `INTC`, `CRCL`, `MSFT`, `INJ`);
- oublier des resultats qui ont demande beaucoup de temps de calcul.

Le dual-track resout ca proprement:

- une piste continue d'exploiter les lanes qui ont deja produit des resultats;
- une piste cherche de nouveaux candidats;
- un historique preserve garde les anciens symboles visibles dans le cockpit.

## Snapshot actuel

Le snapshot doit etre regenere avec:

```powershell
Set-Location D:\trading-agent\backend
python - <<'PY'
from services.onchain.aster.aster_dual_track_research_report import get_aster_dual_track_research_report_preview
r = get_aster_dual_track_research_report_preview(write_snapshot=True)
print(r["summary"])
PY
```

Resultats attendus:

- `LABUSDT` reste un champion a exploiter/reality-check;
- `INTCUSDT`, `CRCLUSDT`, `MSFTUSDT`, `INJUSDT` restent visibles;
- `BTCUSDT`, `ASTERUSDT`, `HYPEUSDT`, `BNBUSDT`, `ETHUSDT`, `PLAYUSDT`, `SOLUSDT` peuvent apparaitre cote exploration selon la watchlist.

## Regles de promotion

Un symbole exploration ne remplace pas un champion historique simplement parce qu'il est nouveau.

Il doit d'abord obtenir:

- assez de trades fermes;
- ROI positif;
- profit factor superieur a `1.3`;
- drawdown acceptable;
- verification mark/index ou qualite data suffisante.

## Garde-fous

- Aucun appel externe.
- Aucun write DB.
- Aucun trade reel.
- Aucun wallet.
- Aucun signal client.
- `write_snapshot=True` ecrit seulement un JSON local de recherche.
