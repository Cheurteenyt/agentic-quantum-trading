# 06 — Data : contrats d’entrepôt (par domaine)

> **Index data** : [`data/README.md`](data/README.md)  
> **Règle** : une base = un domaine d’écriture. Ne jamais joindre FOMO et Aster
> dans le même rapport « officiel » ni mélanger om_v27 avec `klines.db`.

Runtime sous `data/` (gitignored). Ici = **contrat** seulement.

---

## 1. Carte des bases vivantes

### ASTER — `data/warehouse/`

| Base / fichier | Contenu | Écrivains |
|---|---|---|
| `klines.db` | klines 1h/15m (CVD taker), funding, liq_events, oi_history, block_trades, paper_trades Aster, signal_events, flow… | nocturne ASTER, oi-collector, blocktrades, paper_forward |
| `depth.db` | depth_bins ~500 niv × 15 sym (24/7) | aster-depth-collector / depth engine |
| `aster_health_state.json` | watchdog ASTER | aster-health (5 min) |
| `mae_state.json` | moniteur MAE machine | the_machine / nocturne |

Doc détaillée : [`24-donnees-aster.md`](24-donnees-aster.md).

### FOMO — `data/fomo/`

| Base | Contenu | Écrivains |
|---|---|---|
| `fomo.db` | ticks, OHLCV, MC samples, tokens, pre_graduated (HOT daemon) | **seul** écrivain : fomo-ws-daemon (+ topups déclarés) |
| `fomo_swaps.db` | DOM / ws_traders / swaps / parking | worker DOM, swaps-fresh |
| `fomo_rest.db` | snapshots REST, swaps élite, token trades | fomo-rest-collector |
| `fomo_mobula.db` | mémoire topup | mobula-topup |
| `fomo_paper.db` | ledger forward FOMO | fomo-paper-forward |
| `health_state.json` | watchdog FOMO | fomo-health |

Doc : [`23-maitrise-fomo.md`](23-maitrise-fomo.md).

### X — `data/warehouse/x_posts.db`

Registre harvest / scores — écrivain : x-nightly / harvest midi.

### OPENMARKET — hors `data/` repo (local)

| Entrepôt | Doc |
|---|---|
| `om_v27.db` + `data_x501/` CSV | [`26-openmarket-donnees.md`](26-openmarket-donnees.md) |

**Jamais** dans le même BLOC STATS que `the_machine`.

### Legacy (preuve négative)

| Base | Rôle |
|---|---|
| `legacy_lanes.db` | 17k lanes — **100 % PnL > 0 = artefact de survivance** ; test négatif du moteur |

Voir §3. Ne plus traiter comme alpha.

---

## 2. Règles d’écriture (tous domaines)

1. **Un écrivain principal par DB** — backfills = fenêtre exclusive (stop unit vérifié) ; court = WAL + busy_timeout.
2. **Écrire les perdants** dans tout pipeline de recherche (le legacy prouve pourquoi).
3. **Identité obligatoire** à l’insertion (symbole, intervalle, side, risk, exécution, levier…).
4. **Réalisé ≠ latent** — colonnes séparées.
5. **Schema versionné** — pas de compare cross-version sans conversion déclarée.
6. **Horizon de backtest tagué** dans le *rapport* (`H-1Y` / `H-MULTI` / …), pas implicite dans la base.

---

## 3. Legacy lanes — leçon (août, toujours vraie)

Corpus indexé : 17 092 lignes, **0 lane perdante écrite**, 99,6 % < 100 trades,
69,7 % identité incomplète. Ce n’est pas de la recherche, c’est une vitrine.

**Usage unique** : test de régression — un moteur sain doit **rejeter** ce corpus,
pas reproduire +924 kUSD.

```bash
python scripts/index_legacy_dataset.py --stats   # si présent
sqlite3 data/warehouse/legacy_lanes.db
```

---

## 4. Où documenter un changement

| Changement | Doc à mettre à jour le même jour |
|---|---|
| Schéma Aster / collecteur | 24 + cette page (table) |
| Pipeline FOMO | 23 + cette page |
| om_v27 / panel x501 | 26 |
| Nouvelle base | cette page + `docs/data/README.md` |

Pas de dumps bruts dans `docs/`. Audits one-shot → `reports/<domaine>/`.
