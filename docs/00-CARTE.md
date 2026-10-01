# CARTE DU PROJET — un seul endroit pour tout trouver

> Mise à jour : 01/10/2026 (restructure domaines + nettoyage corruption merge).
> Navigation docs : [`docs/README.md`](README.md) · Structure : [`PROJECT_STRUCTURE.md`](../PROJECT_STRUCTURE.md) · Lab : [`lab/README.md`](lab/README.md)

**Domaines** : ASTER ≠ FOMO ≠ OPENMARKET ≠ X — ne pas mélanger métriques ni reports.

| Index doc | Chemin |
|---|---|
| Data (contrats) | [`data/README.md`](data/README.md) |
| Aster | [`aster/README.md`](aster/README.md) |
| FOMO | [`fomo/README.md`](fomo/README.md) |
| OpenMarket | [`openmarket/README.md`](openmarket/README.md) |
| Lab grind | [`lab/README.md`](lab/README.md) |

---

## LA MACHINE & LE REGISTRE (domaine ASTER)

- **Portefeuille officiel** : `scripts/the_machine.py` (nocturne ASTER) — flux : cascade majeurs gated AL + sizing vol-inverse, cascade memecoins, survivor long ; vol_spike_6h optionnel (`--vol-spike`).
- **Chiffres backtest (référence de table, pas une preuve absolue)** : voir `docs/21-goal-performances.md`. Toujours taguer l’horizon (`H-1Y` vs `H-MULTI`).
- **Verdict T8** : les ABSOLUS type +3905 %/an sont des **artefacts de fenêtre / warm-up DB**. Les RELATIFS (ordre des flux, gates) tiennent. Le **paper forward** reste le juge — détail dans `docs/20-registre-indicateurs.md`.
- **Règle levier** : ≤ 100/(maxMAE + 0,5) ; moniteur `data/warehouse/mae_state.json`.
- **Candidat qualité** : cascade ∩ funding-rank-bas (accumulation forward).
- **Registre vivant** : `docs/20-registre-indicateurs.md`.
- **Carte scripts** : `scripts/README.md`.

Reports Aster → `reports/aster/`.

---

## DOMAINE OPENMARKET x501 (isolé)

Programme **100 $ → 50 100 $** (DD ≤ 25 %, zéro intervention autonome).

| Doc | Rôle |
|---|---|
| `docs/25-openmarket-x501.md` | Mission, doctrine, roadmap |
| `docs/26-openmarket-donnees.md` | Entrepôt om_v27 |
| `docs/27-pouvoirs-kscript.md` | Exploitation kScript (**40/53 = 75,5 %** canonique vague 3) |
| `docs/28-protocole-ab-x501.md` | A/B pré-enregistré |
| `docs/29-fill-maker-mesure.md` | Preuve fill maker (révision v21 en review) |
| `docs/30` … `docs/37` | Bancs locaux (flux, absorption, refs, OI, U-shape, LSR) + **horizon de backtest « depuis le début de l'actif » (v29)** |

**MC v20 (baseline officielle tant que review 29 non validée)** : maker δ=2 médiane ~468 $ vs taker ~273 $ — voir docs 25/29 pour nuances et candidat v21.
**Horizon v29 (règle verrouillée)** : backtest depuis le début de l'actif — pool 12 = 3,42 ans, 6 ans sur 9/12, BTC 7,07 ans ; base deep 1 041 871 barres ; fenêtre 23 mois du MC v20 = pire cas du cycle 2019-2026 (docs 37).

Code : `scripts/studies/x501_openmarket/` uniquement.  
Reports : `reports/openmarket/`.  
Index lecture : [`openmarket/README.md`](openmarket/README.md).

**Pivot recherche** : effort R&D prioritaire OpenMarket ; collecteurs Aster/FOMO continuent ; nouvelles *études* Aster/FOMO passent par le lab avec `domain:` explicite.

---

## DOMAINE FOMO

Pipeline ticks / WS / REST / paper — **séparé** de la machine.

- Doc : `docs/23-maitrise-fomo.md` · index [`fomo/README.md`](fomo/README.md)
- Juge : `scripts/fomo_paper_forward.py`
- Reports : `reports/fomo/`

---

## DOMAINE X

Harvest + scoring : `x_harvest.py`, `score_x_calls.py`, nocturne `x-nightly`.  
Reports : `reports/x/`.

---

## COLLECTEURS 24/7 (systemd user)

| Service | Rythme | Domaine | Rôle |
|---|---|---|---|
| `aster-depth-collector` | 24/7 | ASTER | Carnets → depth.db |
| `aster-liq-collector` | 24/7 | ASTER | Liquidations |
| `oi-collector` / `aster-blocktrades` / `aster-premium` | 15 min | ASTER | OI, prints, premium |
| `aster-health` | 5 min | ASTER | Watchdog |
| `fomo-ws-daemon` / `fomo-tick-collector` | 24/7 | FOMO | WS + ticks |
| `fomo-rest-collector` | 30 min | FOMO | REST |
| `fomo-paper-forward` | 15 min | FOMO | Ledger forward |
| `fomo-health` | 5 min | FOMO | Watchdog |
| `trading-agent-nightly` | 03:00 | ASTER | Nocturne machine |
| `x-nightly` | 03:21 | X | Harvest / scores |
| `fomo-nightly` | 03:55 | FOMO | Radar / flows |

Une unit = un domaine — ne pas éditer pendant son run.

---

## ENTREPÔTS (`data/` — gitignored)

| Path | Domaine |
|---|---|
| `warehouse/klines.db` (+ oi, liq, funding, paper Aster…) | ASTER |
| `warehouse/depth.db` | ASTER |
| `warehouse/x_posts.db` | X |
| `fomo/fomo.db`, `fomo_rest.db`, `fomo_swaps.db`, `fomo_paper.db`, … | FOMO |

Contrats doc : [`data/README.md`](data/README.md) · `06-data.md` · `24` · `26` · `23`.

---

## RAPPORTS

| Dossier | Domaine |
|---|---|
| `reports/aster/` | Machine, régimes, paper Aster |
| `reports/fomo/` | Paper / lifecycle FOMO |
| `reports/openmarket/` | Baselines x501 |
| `reports/x/` | Harvest / calls |

Les fichiers encore à la racine de `reports/` sont legacy ; les **nouveaux** vont dans le sous-dossier domaine.

---

## LAB (création d’indicateurs)

[`lab/README.md`](lab/README.md) — hypothèse → étude → registre → mortuary / primitives.  
Sans ça, le catalogue se vide ou l’agent tourne en rond.

---

## RÈGLES

- Aucun ordre autonome — exécution = user seul
- Signal : backtest pré-enregistré avant de croire (`docs/03-methodology.md`)
- Clés dans `.env` (git-ignoré)
- Main protégée : **PR only** (pas de push direct, pas de merge bot)
- FOMO / OpenMarket / Aster : **zéro mélange** de BLOC STATS
