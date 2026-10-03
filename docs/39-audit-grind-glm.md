# 39 · AUDIT R2 & PROTOCOLE DE GRIND — brief pour GLM 5.3 Flash

> **Statut : PROPOSITION.** Les points ⚖ sont des décisions du user (§7) : ne les applique pas seul.
> **Épinglé sur `42b6728`** (03/10/2026 08:53 · 441 commits · PR #1–#35). **`python3 scripts/audit_check.py` fait foi** sur l'état courant ;
> ce document n'est qu'un instantané. Chaque constat porte l'identifiant du contrôle qui le vérifie (B2, F3…).
> Méthode : chaque « fix » annoncé dans un commit a été relu **contre son diff** et rejoué, pas cru sur parole.

## 0. Lis ça d'abord (GLM) — 10 lignes, le reste est de la référence

1. `python3 scripts/audit_check.py` → liste ce qui est encore cassé. **Ne dis jamais « corrigé » sans l'avoir relancé.**
2. Lis `research/STATE.md` (≤ 2,3 Ko). **Pas `docs/20` en entier** (127 Ko) : `grep` ciblé seulement.
3. **AVANT toute expérience** : `python3 scripts/lab_ledger.py check --family F --strategy S --hypothesis "…"`. Sortie 0 = go · 3 = doublon (NO-OP) · 4 = STOP → file B (§4.3).
4. **APRÈS** (FAIL compris) : `lab_ledger.py log … --verdict … --n N --er X --notes "…"`, puis `lab_ledger.py sync-state`. **Les résultats vont dans `--notes`, jamais dans `--params`** (ça fausse le hash de variante).
5. Un verdict = **IC95 par blocs-mois + n_eff**, jamais un E[R] nu ni un « WR 87 % ». Critères PASS/FAIL écrits **avant**.
6. Tout chiffre écrit dans un commit, un doc ou STATE.md porte **sa commande de reproduction**. Sans elle = présumé halluciné (cf. « 87 % WR »).
7. Le modèle local (Bonsai) ne donne **jamais un chiffre ni un verdict** : seulement des affirmations CITÉES, vérifiées par `bonsai_verify.py` (§5).
8. Interdits en session : modifier protocole, coûts (8 bps RT), symboles ou split ; `git push` sur `main` ; tout ordre autonome.
9. **Jamais inactif** : budget épuisé ou doublon → file B. Jamais de variante déguisée.
10. Réponse : verdict chiffré d'abord, puis « prochaine action ». Une session = une hypothèse = un rapport ≤ 40 lignes.

## 1. Verdict en 8 lignes

1. **Le repo a beaucoup avancé** : 28 essais au ledger, CI + hook pre-push + flux PR (#19–#35), `lab_ledger.py`, registre OpenMarket, pré-enregistrements scellés (H-CROWD-1), audit adversarial qui a **réfuté un claim maison** (« 87 % WR » = backtest à 0 bps de coûts), réplication LONG-FLUSH-BOUNCE sur 586 symboles, backfill premium de 557 symboles.
2. **Le plateau est réel** : pool OpenMarket v8 E[R] +0,093 R, IC95 blocs-mois **[−0,027 ; +0,223]**. Branché sur `backtest_v2` (adaptateur réparé, N=362) : **aucun test ne survit à Bonferroni** (t ≥ 3,64 requis ; pool 1,49 ; A3 1,81).
3. **Le grind tourne déjà** : sur 28 entrées, **2 PASS seulement** (`t21_inversion_split`, `t25_resizing_cible`) et **0 sur les 26 autres** ; 22 FAIL. Le goulot est le taux de réussite a priori, pas le débit.
4. **Plusieurs « fix » annoncés ne tenaient pas** : gate du ledger passif (24/20 en permanence), scellé H-CROWD-1 rompu (le script refuse de tourner), adaptateur de multiplicité jamais exécutable, shadow-farm = 4 étiquettes YAML sur 7 annoncées.
5. **Le modèle local aide mais hallucine** : audit de code 5/15 réels (commit) · 6/16 (en-tête) · 4 lignes réelles (tableau) — et « signal/bruit ≈ 50 % » écrit au-dessus de 33-38 %. Il est branché avec `injectAgentsMd: true` (+≈ 1,6 k jetons à chaque appel) et deux sorties ont été **tronquées**.
6. **Le prochain faux positif probable** est `premium-fade-listing` (armé lun 06/10) : sous-famille d'une famille close, trouvée par décomposition des données, n = 77 569 non indépendants, critères sans IC. **À amender AVANT lundi** (§6.2).
7. **La donnée plafonne le rétrospectif** : Aster 13 mois ≈ 0 essai « payable » → forward-only ; base deep 7 ans → rétrospectif possible sous ledger.
8. **Cette PR corrige les défauts vérifiés** (ledger v2, scellé, adaptateur, 2 timeouts, CI bloquante) et ajoute l'outil d'ancrage du modèle local.

## 2. État vérifié des tâches de docs/39 (annoncé → relu dans le diff)

| # | Annoncé | Vérifié | Statut |
|---|---|---|---|
| T1 | 9 chemins `/home/z/` → `X501_EXT_ROOT` | `git grep` : 0 restant (B2 = OK ; mon contrôle se flaguait lui-même, corrigé) | ✅ |
| T3 | « 22 essais backfillés » | 28 entrées ; **aucune** n'a `backfill: true` → l'exclusion du budget (#24) ne s'applique à rien ; v1 affiche **24/20** | ⚠ corrigé (v2) |
| T4 | docs/25 sur MC v31 | B3 = OK | ✅ |
| T5 | CI | existe ; `audit_check … \|\| true` = **jamais bloquante** ; `--fail-on` ajouté | ⚠ corrigé |
| T6 | « 89 fichiers × timeout=60 » | **84 fichiers, 127 appels** (tous `timeout=60`) ; **2 restaient** dans le nocturne (`cascade_funding.py:99`, `edge_regime_monitor.py:21`) | ⚠ corrigé |
| T7 | hypothèses pré-enregistrées | 9 fichiers (dont `holdout-x`, `liq-echo`, `premium-torsion`, `depth-imbalance`) ; les 4 lignes « Hash du gel » sont encore des gabarits (`<commit>`, `<à committer avant le run>`) ; seul H-CROWD-1 est scellé… puis **rompu** (4b31e96) | ⚠ corrigé |
| T8 | adaptateur de multiplicité N=341 | **`ImportError` : `bonferroni_threshold` n'existe pas** — jamais exécuté. Réécrit sur l'API réelle | ❌ → ✅ |
| T9 | « 7 candidats SHADOW » | **4** `status: SHADOW` dans `registry.yaml` ; **aucun code ne lit ce statut** ; pas d'évaluation séquentielle | ❌ |
| D1 | cible mesurée dans l'agent | a9595fd : OK ; mais `bonsai.md` injecte AGENTS.md (§5) | ✅ / ⚠ |
| — | « 773 tests verts » | README : 627 · sandbox : 678 (`--fast`) · commits : 773 — **trois chiffres** ; laisse la CI l'afficher | ⚠ |

## 3. Ce qui ne va pas (constats, preuves, conséquence)

### P1 · Le gate du ledger n'était pas un gate (F1, F2)
Rejoué sur `lab_ledger.py` de `main` : un doublon **reformulé** passe (rc 0, même sous une autre stratégie) ; **6 FAIL dans une famille** (plafond 5) → `GO` ; **21 verdicts NUL / SOUS_PUISSANT / INCONCLU** logués → budget inchangé (seuls PASS/FAIL comptent) ; `per_family` / `per_strategy` n'apparaissent **nulle part** dans le code ; fenêtre glissante de 7 jours (la policy dit « semaine ») ; chaque `log` réécrit tout le fichier ; `log` sans `--date` plantait (corrigé en 42b6728 ; le message de commit écrit : « la commande n'avait jamais marché »).
**Conséquence** : un gate **toujours rouge** (24/20) apprend à l'ignorer — le budget a été dépassé « avec audit tracé ». v2 : semaine ISO, date d'effet = `frozen_tag` de la policy (les 12 essais antérieurs = backfill hors budget → **16/20**), tous les verdicts hors PREREG consomment, plafonds famille/stratégie/variantes appliqués, doublon sur hypothèse **normalisée** quelle que soit la stratégie, append atomique, `selftest` (11 propriétés).

### P2 · Le scellé de H-CROWD-1 a été rompu par son propre amendement (F3)
`crowding_composite.py` grave `EXPECTED_SEAL` (sha256 du fichier d'hypothèse). Le commit 4b31e96 a **ajouté** 11 lignes d'amendements *dans* ce fichier → `sha256 90adb4… ≠ 8df0b1…` → **« [seal] ROMPU », exit 2 à chaque exécution**, donc le tir du 30/10 n'aurait pas tourné. L'original (f5bbcd2) colle bien au scellé. Réparé : original restauré, amendements dans un **fichier séparé** scellé à part (`EXPECTED_AMEND_SEAL`), script et test `test_hypothesis_seals.py` vérifient les deux. **Règle : on amende par ajout, jamais en éditant le fichier scellé.**

### P3 · L'adaptateur de multiplicité n'avait jamais produit un chiffre (F4)
`from … import bonferroni_threshold` : le nom n'existe pas (l'API réelle : `bonferroni`, `benjamini_hochberg`, `sharpe_pvalue`, `deflated_sharpe_ratio`, `audit_campaign`). Version corrigée : `ppy` = trades/an ⇒ `sharpe_pvalue` redonne le t de Student ; `n_obs = n_eff` (blocs-mois) corrige la corrélation entre symboles ; N = 341 cellules citées + ledger hors openmarket = **362** ; DSR **non calculé** (la variance des Sharpe d'essais n'existe pas — ne pas l'inventer).
Résultat : POOL t blocs 1,49 (p = 0,068) · A3 1,81 (0,035) · A4 1,41 · A1 −1,23 → **0 survivant**, seuil unilatéral t ≥ 3,64.

### P4 · La shadow-farm n'existe qu'en étiquettes (T9)
4 `status: SHADOW` (`machine_cascade_majors`, `machine_cascade_meme`, `machine_survivor_long`, `machine_vol_spike_6h`). INV-C/J/N ne sont pas au registre. Aucun `.py` de `scripts/` ne lit « SHADOW » (les occurrences trouvées sont `SHADOW_DDL` d'un moteur de profondeur et du code on-chain sans rapport). **Rien n'évalue séquentiellement ces candidats.**

### P5 · Le plateau statistique (D1, D1b, D2, D3)
Recalcul sur `trades_v8_deep.csv` (t blocs = erreur-type clusterisée par mois d'entrée) :

| Sous-ensemble | n | E[R] | t iid | t blocs | n_eff |
|---|---:|---:|---:|---:|---:|
| **Pool entier** | 868 | +0,093 | 2,31 | **1,49** | 362 |
| IS < 2023-12-28 | 404 | +0,033 | 0,53 | 0,33 | 150 |
| OOS ≥ 2023-12-28 | 464 | +0,144 | 2,80 | 2,01 | 238 |
| A1 / A3 / A4 | 179 / 164 / 525 | −0,093 / +0,210 / +0,119 | −1,15 / 2,21 / 2,29 | −1,23 / 1,81 / 1,41 | 179 / 111 / 198 |
| 2026 seul / hors 2026 | 153 / 715 | +0,308 / +0,047 | 3,00 / 1,08 | 2,82 / 0,68 | 135 / 286 |

Les 43 meilleurs trades (5 %) font 166 % du total ; sans eux E[R] = −0,065. MC v31 : P(×501 en 12 mois) = 0,00 % ; médiane des maxDD simulés 24,9975 % (plancher mécanique du simulateur, noyau `simulate_ratchet` toujours absent de git : B1).

### P6 · Pré-enregistrement `premium-fade-listing` : les 5 trous (armé lun 06/10)
Lu en entier (54 lignes) et comparé à `premium_fade_full_remeasure.py` (0 occurrence de bootstrap / cluster / IC) :
1. **Famille close rouverte par une coupe** : `premium_fade_full` est FAIL (naked −9,6 bps ; le fade brut ≈ +1 bp contre 8 bps RT). La coupe « < 90 j » est apparue **en décomposant les données** qui donnent +8,8 bps (le fichier l'écrit lui-même). Le nombre de coupes explorées n'est pas loggué : c'est du N de multiplicité caché.
2. **n = 77 569 n'est pas la taille d'échantillon** : les trades (symbole × barre) d'un même jour sont corrélés. En iid tout écart minuscule est « significatif » ; l'unité indépendante est le jour × cohorte de listings. Aucun critère P1–P6 ne porte d'IC clusterisé.
3. **P6 (≥ 60 % de mois positifs en VAL)** : VAL = 30 % de la plage ; si elle couvre quelques mois, 60 % de 3-4 points ne signifie rien.
4. **Le seuil |Δindex_15m| ≤ 0,5 % vient d'une « simulation adversariale » Bonsai** (le fichier : « PAS dérivée de nos données ») : un petit modèle quantifié n'est pas une théorie. Sur des listings volatils, 15 % de violations est probablement dépassé **par construction** : le KILL serait un verdict sur le seuil, pas sur l'edge.
5. **Pas de contrôle de faisabilité sans rendement** : la part de barres que ce filtre écarte se mesure **sans regarder un seul P&L** — elle ne consomme rien et évite un KILL prévisible.

### P7 · Hygiène et ce que la CI ne voit pas (F5, F6)
STATE.md était périmé (22 entrées, « 13/20 ») pendant que le ledger en avait 28 ; sa source de chiffre (« +24 %/26 j @ DD 3,4 % », docs/20 l.291) tient sur 26 jours — aucune information sur le DD. Désormais le bloc LEDGER est **généré** (`sync-state`) et `audit_check F5` échoue s'il est périmé. docs/20 = 692 lignes / 127 Ko. `params` du ledger détourné pour stocker des résultats (3 entrées).

## 4. Le protocole de grind (version courante)

### 4.1 Principes
Budget = hypothèses **comptées** (20/semaine ISO, 5/famille, 3/stratégie, 12 variantes), pas du CPU · une hypothèse = un fichier pré-enregistré commité **avant** le code · une variante se juge **contre le champion, en différence appariée** · résultat → modification = nouvelle génération = nouveau test · tout se logue, FAIL compris.

### 4.2 Où grinder
Bonferroni : t*(N) = Φ⁻¹(1 − α/2N), il faut t* ≤ SR·√années.

| N | t* (bilatéral) | SR min 13 mois (Aster) | SR min 7 ans (deep) |
|---:|---:|---:|---:|
| 1 | 1,96 | 1,88 | 0,74 |
| 10 | 2,81 | 2,70 | 1,06 |
| 100 | 3,48 | 3,34 | 1,32 |
| 362 | 3,81 | 3,66 | 1,44 |

Aster 13 mois : 0 / 0 / 1 essai « payable » (SR 1,0 / 1,5 / 2,0) → **forward-only**. Base deep 7 ans : 6 / 692 / 412 149 → rétrospectif possible sous ledger. Couches propriétaires (depth, liquidations, whales, X) : courtes → forward. *(Hypothèse iid, Bonferroni conservateur ; l'ordre de grandeur tient avec BH/DSR.)*

### 4.3 Boucle A (budgétée) et boucle B (jamais inactif)
**A** : `audit_check` → STATE.md → 1re hypothèse de `research/hypotheses/` → `lab_ledger check` → commit du fichier d'hypothèse → run (une variable, contrôle inverse, baseline) → verdict IC95 blocs-mois + coûts ×1,5 + hors top 5 % → `log` + `sync-state` → FAIL = on s'arrête, famille à ≥ 3 FAIL et 0 PASS = fermée.
**B** (non budgétée, aucune nouvelle hypothèse) : tâches du §6 · pré-enregistrer les 5 prochaines hypothèses (sans les lancer) · mesures de faisabilité **sans rendements** · qualité des données · re-mesure d'un candidat sous d'autres coûts/fenêtres (re-mesure, jamais retune) · évaluation forward des candidats en shadow.

### 4.4 Règles de décision
Mesure = E[R] net + IC95 bootstrap par blocs-mois + n_eff. Preuve rétrospective = borne basse > 0 **et** |t blocs| ≥ t*(N cumulé du ledger) ; sinon CANDIDAT → shadow forward. Variante vs champion : différence appariée + IC95. Toujours positif aux coûts ×1,5 et hors top 5 %. Puissance : si l'edge détectable dépasse l'edge visé → SOUS_PUISSANT (pas FAIL) ; N minimal par **erreur-type**, pas par n fixe (n ≥ 10 par quadrant, OOS n ≥ 20 : SE = 0,26 R à n = 20 avec sd 1,18).

## 5. Le modèle local (Bonsai 27B, RTX 3070 8 Go) — comment s'en servir sans qu'il hallucine
**Constats mesurés** : (a) `bonsai.md` : `injectAgentsMd: true` → AGENTS.md (240 lignes, 5 636 o ≈ 1,6 k jetons) ajouté à **chaque** appel, alors que le prompt dit « tu n'as pas accès au disque ni aux outils » : instructions contradictoires + contexte gaspillé. (b) Sorties **tronquées** : audit de code « tronquée à 1800 tokens » ; design PREMIUM-MM « ROI … tronqué à cause du budget de tokens ». (c) Filtrage GLM incohérent : 5/15 (commit), 6/16 (en-tête), 4 lignes réelles (tableau). (d) Tournoi de prédictions : 4 paris ; **INV-C = PASS à 85 %** alors que le ledger donne 2 PASS sur 28 entrées et aucun sur les 26 autres (taux de base PASS 7 %, FAIL 79 %) ; deux autres paris (FAIL 75 % / 80 %) = le taux de base. « Siège d'oracle à 4/4 » : avec n = 4, aucune calibration n'est mesurable. (e) Un design de stratégie (15 m, levier 3,33×, « sweet spot ») **sans backtest committé** ; le chiffre associé (« 87 % WR, +21 %/an @ 3,33× ») n'existait dans **aucun code** et s'est effondré à coûts réalistes (fade brut ≈ +1 bp contre 8 bps RT ; l'audit : « le backtest source tournait coûts 0 bps »).
**Pourquoi** (inférence, à tester) : ≈ 27 G de paramètres à ≈ 2 bits ≈ 7 Go ⇒ presque rien de VRAM pour le cache KV ⇒ le contexte doit rester court de toute façon ; la qualité d'un modèle aussi quantifié baisse avec la longueur.
**Règles** :
1. **Sans état, une tâche par appel**, ≤ ≈ 2,5 k jetons en entrée, ≤ 800 en sortie, jamais d'historique de chat. Code : découpé par `bonsai_verify.py chunks FICHIER --lines 100` (lignes numérotées).
2. **Il ne produit que des affirmations citées** : `[{"id","claim","file","line","quote"}]`, `quote` verbatim ≥ 12 car. `bonsai_verify.py verify claims.json --task code-audit` marque GROUNDED / MISPLACED / UNGROUNDED / BAD_REF / VAGUE **mécaniquement** ; seul GROUNDED va au juge. Le décompte n'est plus tapé à la main : `bonsai_verify.py score`.
3. **Jamais un chiffre, jamais un verdict, jamais un seuil.** Les nombres viennent de scripts. Un seuil « de théorie » issu de Bonsai n'est **pas** a priori.
4. **Auto-cohérence** : 3 tirages (température 0,3-0,7), garder les affirmations présentes dans ≥ 2 (même fichier, ±8 lignes) — lancé la nuit.
5. **Décider par la mesure** : un type de tâche n'est utilisé que si la précision de bout en bout ≥ 70 % sur ≥ 30 affirmations jugées (`score` affiche la borne basse). Aujourd'hui : code-audit ≈ 33-38 %.
6. **Prédictions** = probabilités loggées, comparées au taux de base (Brier) après ≥ 20 résolutions ; un modèle qui dit « FAIL 79 % » ne bat pas le taux de base.
7. **Config** : `injectAgentsMd: false` (commit séparable, ⚖ D7) ; `thoughtLevel` bas pour l'extraction ; **rejeter toute sortie tronquée** (`finish_reason == "length"`) ; pour les designs, budget de sortie suffisant.
8. **A/B contexte** : même tâche à 2 k / 4 k / 8 k jetons, mesurer le taux GROUNDED, garder le plus grand contexte où la précision tient. Une soirée de calcul.
9. **Rôle** : générateur d'idées (mécanisme en texte → `research/hypotheses/_inbox/`, non validé) et critique adversariale d'un pré-enregistrement (affirmations ancrées). **Pas** juge, pas source de chiffres.

## 6. Tâches pour GLM (dans l'ordre, critère d'acceptation vérifiable)
| # | Tâche | Acceptation |
|---|---|---|
| R1 | **Amender `premium-fade-listing` AVANT lundi** (§6.2) — fichier d'amendements séparé, scellé | `audit_check` F3 = OK ; amendements commités avant le run |
| R2 | **Shadow-farm réelle** : un script nocturne lit les entrées `SHADOW`/forward, applique un test séquentiel (SPRT ou e-value) + FDR global, écrit un verdict par candidat ; ajouter INV-C/J/N au registre | ≥ 7 candidats évalués chaque nuit, résultat dans le rapport nocturne |
| R3 | **Exécuter HOLDOUT-X** (`research/hypotheses/holdout-x.md` est écrit, **jamais exécuté**, 0 entrée au ledger, « Hash du gel » encore `<à committer avant le run>`) : sceller le fichier, collecter ≥ 40 symboles jamais utilisés (le backfill de 557 symboles prouve que c'est faisable), puis un seul run ; ajouter « sinon INCONCLUSIF → étendre » aux critères | 1 verdict loggué ; hash réel dans le fichier |
| R4 | **Mesure de coûts par symbole/heure** (depth, fills) sur données indépendantes des résultats, déclarée puis figée | table de coûts commitée + hash |
| R5 | **Noyau MC** : committer `x501_mc_v10/11/12.py` ou déclarer v30/v31 « NON REPRODUCTIBLES » ; ajouter une variante **sans plancher à 25 %** | B1 = OK ou statut explicite |
| R6 | **Hook orchestrateur** : refuser de lancer un script d'expérience si `lab_ledger check` ≠ 0 | E1 devient une contrainte |
| R7 | **A/B contexte Bonsai** (§5.8) + premier `score` sur ≥ 30 affirmations | précision par taille de contexte dans STATE.md |
| R8 | **Compteur de tests unique** (CI) : retirer 627 / 678 / 773 des docs | 1 seul chiffre, généré |
| R9 | Backfill des « coupes explorées » de la décomposition listing dans le ledger (N caché) | entrées loggées |

### 6.2 Amendements proposés à `premium-fade-listing` (avant lundi, fichier séparé scellé)
(a) **Pré-contrôle sans rendement** : part des barres listing < 90 j écartées par |Δindex_15m| > 0,5 %, **sans lire un P&L** ; si > 15 % d'avance, le seuil n'est pas testable → le revoir **avant** de sceller. (b) **IC95 clusterisé par jour** (et par symbole) sur l'espérance VAL, borne basse > +2 bps ; n_eff reporté. (c) **P6** remplacé par : « nombre de jours VAL ≥ 40 et part de jours positifs » (pas des « mois »). (d) **Registre des coupes** : combien de découpages ont été regardés avant « < 90 j » ; compté dans N (t* du ledger). (e) Traiter la famille comme **sous-famille de `premium_fade_full`** dans le ledger (même plafond de famille).

## 7. Décisions ⚖ qui t'appartiennent
- **D2 · Mining rétrospectif** : le SKILL dit « FERMÉ » ; tu veux grinder. Proposition : autorisé sur la base deep 7 ans **sous ledger + t*(N)**, interdit sur Aster 13 mois (forward-only).
- **D3 · `protocol_v2`** (toujours PROPOSITION) : ratifier en ajoutant un critère de preuve agrégée (borne basse IC95 blocs-mois > 0, |t| ≥ t*(N)). Le critère 5/6 laisse passer 11 % des tests à edge nul.
- **D4 · Holdout** : déclarer le pool v8 « brûlé » sur ses 40 symboles et ses années ; seuls tests propres = HOLDOUT-X et le forward.
- **D5 · Modèle** : `GLM-5.3-Flash` pour exécuter un banc entièrement spécifié ; les hypothèses et les tâches R2, R5, R6 demandent plus fort ou toi.
- **D6 · « Non-stop »** : le plafond de 20/semaine compte des hypothèses. Non-stop = file A tant que le budget le permet, puis file B et shadow-farm. Le relever fait monter t*(N).
- **D7 · Bonsai** : `injectAgentsMd: false` (commit séparé de la PR) et adoption du protocole §5.
- **D8 · Cible** : ×501 (docs/25) reste mesuré inatteignable (MC v31 : P = 0,00 %) ; à garder comme horizon ou à remplacer par un critère de robustesse.

## Annexe A · Méthode
t blocs-mois = Σ_mois(R − E[R]) puis racine de la somme des carrés / n ; n_eff = n / deff, deff = (SE blocs / SE iid)² ; bootstrap par blocs : 4 000 tirages de mois. `x501_multiplicity_adapter.py` : sharpe annuel = E[R]/sd·√(trades/an) → `sharpe_pvalue(…, n_obs = n_eff)`. Tout se rejoue par `audit_check.py` et `x501_multiplicity_adapter.py`.

## Annexe B · Limites
Je n'ai **pas relancé les backtests** (`data/` hors git, noyau MC absent) ; aucune recherche de look-ahead dans les moteurs. Je n'ai pas accès aux données listing / premium : P6 est une critique de **méthode**, pas un résultat. Les numéros de t sont ceux du CSV de trades committé ; les blocs-mois corrigent la corrélation intra-mois, pas inter-mois. N_max suppose iid et un SR vrai hypothétique ; « base-rate faible des features standard » est une inférence cohérente avec 0/26, pas une démonstration. Les raisons de la dégradation du modèle local (§5) sont des hypothèses à tester (A/B contexte). Analyse méthodologique ; rien ici n'est un conseil financier.
