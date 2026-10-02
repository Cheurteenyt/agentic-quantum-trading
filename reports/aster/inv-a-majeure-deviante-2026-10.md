# INV-A — LA MAJEURE DÉVIANTE (pré-enregistrement + résultats)

> **domain: ASTER** · timeframe: 1h · 2026-10-02 · tag `freeze-2026-10-02` · gouvernance : docs/38-gouvernance-recherche.md
> Statut budget : 1 expérience consommée (famille cross-sectional/majors). Aucune itération autorisée après verdict.

---

## PARTIE 1 — PRÉ-ENREGISTREMENT (gelé avant tout résultat ; sha256 du bloc ci-dessous recopié dans les résultats)

### Hypothèse pré-déclarée

Sur le panel des 6 majeures (BTC, ETH, SOL, BNB, XRP, DOGE) en 1h :
- la déviante-**haut** (z ≥ +2) **décrote vs le pack** sur 24-72h (mean-reversion relative) ;
- la déviante-**bas** (z ≤ −2) **rebondit vs le pack** sur la même fenêtre.

### Construction (inputs bruts, aucun indicateur réemployé)

- Données : `data/warehouse/klines.db` (LECTURE SEULE, mode=ro), klines 1h des 6 majeures. Fenêtre panel commune : 2025-09-23 22:00 → 2026-10-01 01:00 UTC (bornée par BNB/DOGE ; continuité horaire vérifiée, 0 gap).
- `ret24_i(t) = close_i(t) / close_i(t−24h) − 1` (rendement 24h du symbole i).
- `z_i(t) = (ret24_i(t) − médiane_pack(ret24)) / σ_pack(ret24)` avec médiane et σ (ddof=1) calculées sur les **6** valeurs ret24 à l'heure t.
- Événement : chaque couple (t, i) avec **|z_i| ≥ 2** — SEUL seuil pré-déclaré, zéro grille. Si plusieurs majeures dévient la même heure, chacune est un événement (règle pré-déclarée).
- Trade relatif, **sans levier**, notional 1 par jambe (short i / long pack ou l'inverse) :
  - déviante-haut : PnL brut = `médiane_pack(H) − ret_i(H)` (short i vs pack) ;
  - déviante-bas : PnL brut = `ret_i(H) − médiane_pack(H)` (long i vs pack) ;
  - `ret_x(H)` = rendement de open(t+1) à open(t+1+H) ; `médiane_pack(H)` = médiane des 6 ret_x(H) (incluant i, même définition que l'indicateur).
  - **net = brut − 36 bps** (2 jambes taker 18 bps RT par paire).
- Convention d'exécution docs/38 : signal close(t) → entrée open(t+1) → sortie au plan.

### Protocole immutable

- Split **60/40 chrono GLOBAL** sur la fenêtre d'événements [2025-09-24 22:00, 2026-09-28 01:00] (fin imposée par l'horizon 72h le plus long vs fin de panel). Frontière unique = début + 0,6 × durée. Train = découverte ; **val jamais regardée avant le verdict final**.
- Purge pré-déclarée : événement en train ⟺ t + 72h ≤ frontière ; événement en val ⟺ t ≥ frontière ; tout événement dont l'horizon chevauche la frontière est jeté (ni train ni val).
- Horizons : **48h = horizon PRIMAIRE** (centre de la bande 24-72h) ; 24h et 72h rapportés en contexte pré-déclaré, aucun seuil, aucune sélection.
- Coûts 36 bps RT par événement. Pas de levier, pas de funding (hors périmètre, pré-déclaré). Liquidations : 0 par construction (spread relatif 1x).
- Puissance : **n train ≥ 100 requis** ; sinon « sous-puissant, non tranchable » déclaré tel quel (ce n'est PAS un PASS).
- Robustesse (1 seule variante autorisée, pré-déclarée, train seulement, jamais un second seuil de décision) : recompte au seuil |z| ≥ 2,2.
- Bloc stats mensuel obligatoire sur train et val (n, WR net, bps nets cumulés, pire/record mois, mois négatifs ; DD sur série mensuelle non composée).

### PASS / FAIL (écrits AVANT l'exécution)

- **PASS = les 3 requis, en train ET en val :**
  1. espérance relative **nette > 0** à 48h (train et val séparément) ;
  2. **gradient monotone** des terciles de |z| (force de déviance) : espérance nette croissante T1 → T3 en train et en val ;
  3. **contrôle inverse battu** : espérance de la continuation (position inversée, mêmes coûts) < espérance de la réversion, en train ET en val — sinon ARTEFACT.
- **FAIL = tout le reste** → « FAIL — hypothèse réfutée », gravé, sans itération (pas de deuxième seuil, pas de fenêtre alternative ; budget = 1 expérience, docs/38 : un FAIL ne se répare pas).

### Vérification registre (docs/38, avant départ)

- `research/registry.yaml` : aucune entrée INV-A / déviance de pack au 2026-10-02 (28 entrées, aucune sur cette hypothèse) → expérience nouvelle autorisée, non-dupliquée. Entrée ajoutée au registre après verdict.

---

## PARTIE 2 — RÉSULTATS (remplies après exécution du one-shot ; la Partie 1 ci-dessus était déjà écrite et gelée)

> **Seal de pré-enregistrement** : fichier écrit AVANT tout calcul, 55 lignes,
> sha256 = `0a59f1651e169c110c6198cc085a3dbd843cdc43b077f41bdcfe19421b0c21bc`.
> Script : `scripts/studies/inv_a_majeure_deviante.py` (DB ouverte mode=ro, aucun indicateur réemployé).

### Exécution

- Panel commun 6 majeures 1h : 8 932 heures (2025-09-23 22:00 → 2026-10-01 01:00 UTC), 0 gap, ret24 sur closes, forward sur **vrais opens** (open(t+1) → open(t+1+H)).
- Événements |z| ≥ 2 : **2 034** (haut 1 280 / bas 754). **0 heure multi-déviantes** → la singularité « la majeure au z extrême » n'a jamais été ambiguë. Répartition : DOGE 588, XRP 416, SOL 378, BNB 339, ETH 192, BTC 121.
- Split 60/40 chrono global : frontière 1777834800000 (2026-05-03 ~03:00 UTC) ; **train n = 1 129**, **val n = 895**, purgés (chevauchement 72h) = 10. n train ≥ 100 → **expérience puissante, tranchable**.
- Discipline : TRAIN regardé seul d'abord (INV_TRAIN_ONLY=1), verdict train posé, VAL déverrouillée ensuite.

### Horizon primaire 48h — net (36 bps RT déduits)

| Bloc | n | moyenne | WR | médiane | p05 / p95 |
|---|---|---|---|---|---|
| TRAIN réversion | 1 129 | **+3,5 bps** | 49,4 % | −2,8 | −614 / +592 |
| TRAIN continuation | 1 129 | −75,5 bps | 28,5 % | −69,2 | −664 / +542 |
| VAL réversion | 895 | **−39,5 bps** | 38,0 % | −33,6 | −428 / +342 |
| VAL continuation | 895 | −32,5 bps | 36,1 % | −38,4 | −414 / +356 |

Brut 48h : +39,5 bps en TRAIN (mangé par les 36 bps de coûts) → **−3,5 bps en VAL** (en VAL la déviante CONTINUE légèrement).

### Gradient terciles de |z| (48h net)

| Tercile | TRAIN | VAL |
|---|---|---|
| T1 (déviance faible) | +9,4 bps (WR 48 %) | −48,3 bps (WR 33 %) |
| T2 | +9,7 bps (WR 49 %) | −54,1 bps (WR 35 %) |
| T3 (déviance extrême) | **−8,8 bps** (WR 51 %) | −15,9 bps (WR 46 %) |

Non monotone des deux côtés — en TRAIN le tercile le plus extrême est le PIRE (l'inverse de l'hypothèse).

### Contexte pré-déclaré 24h / 72h (net, réversion)

| Horizon | TRAIN | VAL |
|---|---|---|
| 24h | −18,4 bps (WR 44,0 %) | −39,0 bps (WR 35,3 %) |
| 48h (primaire) | +3,5 bps (WR 49,4 %) | −39,5 bps (WR 38,0 %) |
| 72h | +3,9 bps (WR 45,8 %) | −42,7 bps (WR 38,9 %) |

### Signes séparés (48h net)

- Déviante-haut (z ≥ +2) : TRAIN −23,7 bps (n=675, WR 53 % — asymétrie négative typique du short-vainqueur) ; VAL −33,2 bps (n=598, WR 42 %).
- Déviante-bas (z ≤ −2) : TRAIN **+43,9 bps** (n=454, WR 45 %) — le rebond existe en train ; **VAL −52,1 bps** (n=297, WR 29 %) — mirage de régime, anéanti hors train.

### Robustesse unique |z| ≥ 2,2 (TRAIN, info)

n=431, moyenne **−6,9 bps** (WR 50,6 %), gradient encore plus inversé (T3 −29,6). Aucun signe de renforcement avec l'extrémisme.

### BLOC STATS mensuel (48h net, réversion ; bps = somme non composée par événement à notional 1x ; 0 liquidation par construction)

TRAIN (8 mois, 4 négatifs, pire −19 964 bps, record +22 706 bps) :

| Mois | n | WR | Σ bps | Moy. bps |
|---|---|---|---|---|
| 2025-09 | 26 | 65 % | +403 | +15,5 |
| 2025-10 | 194 | 47 % | −2 042 | −10,5 |
| 2025-11 | 161 | 54 % | +327 | +2,0 |
| 2025-12 | 159 | 67 % | +17 869 | +112,4 |
| 2026-01 | 190 | 39 % | −15 104 | −79,5 |
| 2026-02 | 146 | 60 % | +22 706 | +155,5 |
| 2026-03 | 126 | 45 % | −292 | −2,3 |
| 2026-04 | 127 | 29 % | **−19 964** | −157,2 |

VAL (5 mois, 3 négatifs, pire −30 220 bps, record +22 801 bps) :

| Mois | n | WR | Σ bps | Moy. bps |
|---|---|---|---|---|
| 2026-05 | 182 | 31 % | −9 353 | −51,4 |
| 2026-06 | 185 | 25 % | −18 568 | −100,4 |
| 2026-07 | 173 | 41 % | +31 | +0,2 |
| 2026-08 | 193 | 30 % | **−30 220** | −156,6 |
| 2026-09 | 162 | 68 % | +22 801 | +140,7 |

Le profil mensuel est une loterie de régime (déc-janv-fév vs avr-mai-juin) : aucune stabilité, garde-fou composé-des-mois hostile.

### Verdict — checklist PASS (les 3 requis, TRAIN et VAL)

1. Espérance nette 48h > 0 : TRAIN +3,5 bps ✓ (marginal) / VAL −39,5 bps **✗** ;
2. Gradient terciles |z| monotone croissant : TRAIN inversé **✗** / VAL non monotone **✗** ;
3. Contrôle inverse battu : TRAIN ✓ (+3,5 > −75,5) / VAL **✗** (−39,5 < −32,5 : la continuation bat la réversion → artefact).

## **FAIL — hypothèse réfutée.**

La réversion relative des majeures déviantes existe en brut en train (~+40 bps à 48-72h vs le pack) mais elle (a) ne paie pas les 36 bps RT, (b) n'est pas monotone en force de déviance — les plus extrêmes régressent le moins, (c) disparaît intégralement en validation (brut négatif, continuation gagnante). Aucune itération : pas de second seuil, pas de fenêtre alternative, budget = 1 expérience (docs/38). Entrée registre : `inv_a_majeure_deviante` → REJECTED.
