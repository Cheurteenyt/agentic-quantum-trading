# Structure du projet — domaines, horizons, lab

**Carte vivante** → [`docs/00-CARTE.md`](docs/00-CARTE.md)  
**Onboarding** → [`docs/01-onboarding.md`](docs/01-onboarding.md)  
**Méthodologie** → [`docs/03-methodology.md`](docs/03-methodology.md)  
**Lab grind (création d’indicateurs)** → [`docs/lab/README.md`](docs/lab/README.md)

---

## Règle n°1 — Quatre domaines, zéro mélange

| Domaine | Code / scripts | Données | Nocturne / timers | Rapports |
|---|---|---|---|---|
| **ASTER** (perp maison) | `the_machine`, `anti_liq`, `paper_forward`, `aster_*`, `backtest_*` (harnais) | `data/warehouse/`, `klines.db` | `trading-agent-nightly` | `reports/aster/` |
| **FOMO** (memecoin / whales) | `fomo_*`, `swaps_forward_*`, `derek_*`, `bonding_*` | `data/fomo/` | `fomo-nightly` + timers fomo | `reports/fomo/` |
| **OPENMARKET x501** | `scripts/studies/x501_openmarket/` | caches kScript / local | QA one-shot, pas le nocturne Aster | `reports/openmarket/` |
| **X** (social) | `x_harvest`, `fetch_x_posts`, `score_x_calls` | couches X | `x-nightly` | `reports/x/` |

**Interdit :**
- Comparer un ROI FOMO à un ROI Aster dans le même tableau “officiel”
- Brancher un signal FOMO dans `the_machine` sans étude + registre dédiés
- Mettre un résultat OpenMarket dans le BLOC STATS de La Machine
- Un seul markdown qui mélange les quatre sans sections étanches

Chaque domaine a son **registre de vérité** et ses **garde-fous**. Le point d’entrée global reste `docs/00-CARTE.md`, mais les chiffres ne traversent pas les frontières.

---

## Règle n°2 — Horizons de backtest (ne pas mélanger)

Tout run de backtest / étude **déclare** un horizon :

| Tag | Fenêtre typique | Usage |
|---|---|---|
| `H-1Y` | ~1 an glissant | calibration machine historique, paper aligné |
| `H-MULTI` | multi-années (ex. 2022→) | robustesse régime, **pas** le chiffre “officiel machine” seul |
| `H-LIVE` | forward paper / live window | juge réel |
| `H-MICRO` | jours / semaines (depth, walls) | microstructure uniquement |

**Interdit :** coller un +N% `H-MULTI` à côté d’un +M% `H-1Y` sans label, ou “améliorer” La Machine en changeant l’horizon sans le dire.

Convention dans rapports et registre :

```text
horizon: H-MULTI | window: 2022-01 → 2026-09 | domain: ASTER
```

---

## Règle n°3 — Lab grind (indicateurs qui s’améliorent)

Voir [`docs/lab/README.md`](docs/lab/README.md).

```
Rail A  génération (hypothèse non-standard)
Rail B  falsification (méthodo existante)
Rail C  mémoire (mortuary + primitives + méta)
```

Sans rail C, le catalogue se vide et on tourne en rond.

---

## Arborescence logique (cible)

```text
agent/                 # risk, state, client API — pas de stratégie métier
backend/               # API routers/services (god-files = dette connue)
scripts/
  # noyau ASTER (ne pas casser)
  the_machine.py, anti_liq.py, portfolio_sim.py, stacked_portfolio.py,
  backtest_indicators.py, paper_forward.py, ...
  # FOMO (préfixe fomo_* / swaps_* / derek_*)
  # X (x_*, fetch_x_*, score_x_*)
  studies/             # one-shots vivants
    x501_openmarket/   # domaine OpenMarket ENTIER
  archive_studies/     # études closes (NUL/CONTEXTE)
  archive/             # legacy
docs/
  00-CARTE.md          # index global
  20-registre-*.md     # vérité indicateurs (tous domaines, sections)
  lab/                 # protocole grind, mortuary, primitives
  25/26/28…            # OpenMarket
  23-maitrise-fomo.md  # FOMO
  24-donnees-aster.md  # Aster data
reports/
  aster/               # machine, régimes Aster, paper Aster
  fomo/                # paper fomo, lifecycle
  openmarket/          # baselines x501
  x/                   # harvest / calls
  _legacy/             # anciens à la racine reports/ (à ranger)
data/                  # gitignored — warehouse, fomo, state
tests/                 # unittest stdlib
```

**Phase actuelle de cette PR :** conventions + `docs/lab/` + layout `reports/` + carte.  
**Pas** de `git mv` massif des scripts (casse systemd + imports). Les préfixes de noms et les dossiers `studies/` / `archive_studies/` restent la frontière opérationnelle.

---

## Où écrire quoi

| Besoin | Emplacement |
|---|---|
| Nouvelle hypothèse d’indicateur | `docs/lab/hypotheses/` + `scripts/studies/` |
| Null / ne pas retenter | `docs/lab/mortuary.md` + registre 20 |
| Primitive encore vivante | `docs/lab/primitives.md` |
| Chiffre machine officiel | `reports/aster/` + nocturne ASTER seulement |
| Baseline OpenMarket | `reports/openmarket/` seulement |
| Paper FOMO | `reports/fomo/` + timers fomo |

---

## Migration reports (cette PR)

Les fichiers déjà à la racine de `reports/` restent lisibles ; les **nouveaux** rapports doivent aller dans le sous-dossier domaine. Un index par domaine est fourni sous `reports/*/README.md`.
