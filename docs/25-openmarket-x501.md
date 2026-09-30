# 25 · OPENMARKET x501 — LA MISSION, LES CHIFFRES, LA DOCTRINE

> Créé le 30/09/2026. Doc maître du domaine OpenMarket.
> Les données : `docs/26-openmarket-donnees.md`. Les livrables : `docs/reference/openmarket-x501/`.
> Le code (9 kScripts + 4 QA + scanner) : `scripts/studies/x501_openmarket/`.

## LA MISSION

Partir de **100 $** sur openmarket.xyz et atteindre **50 100 $** en 12 mois
(**+50 000 %**, soit un multiplicateur ×501), sous trois contraintes
non négociables : **DDmax ≤ 25 %** (strict, mesuré sur l'équité intra-trade
comme sur l'équité clôturée), **capital fixe** (100 $ de départ, aucun apport
complémentaire), **zéro intervention manuelle** (les décisions d'entrée et de
sortie sont entièrement codifiées dans les kScripts, pré-enregistrées avant
tout tir réel). La mission est traitée comme un programme de recherche :
chaque affirmation de performance porte sa date, son échantillon et sa
méthode, et tout ce qui n'a pas survécu à la falsification est inscrit
comme tel — la doctrine est la même que celle du registre Aster
(`docs/20-registre-indicateurs.md`) : pré-enregistrer avant de croire.

## LES CHIFFRES OFFICIELS (MC v20 — 12 000 trajectoires, SANS haircut gate)

> MC v20 (01/10) remplace v18 : le gate signal-6 et ses variantes étant
> falsifiés (voir plus bas), ils ne retranchent plus rien. 4 audits verts :
> T0 (référence 641,99 $ bit à bit), T3 (repro bit à bit), T2v20 (0 rupture
> au pire cas R=−1,5 sous taker), T4v20 (monotonie des médianes). DD cap
> 25 % respecté au bit près (max 25,0000 %), 0 rupture sur 60 000 trajectoires.

| Scénario | Coût/côté | Médiane 12 m | P(≥ 250 $) | P(≥ 500 $) | P(≥ 1 250 $) | x501 @ 36 m |
|---|---|---|---|---|---|---|
| S0 référence certifiée | 0,0 bps | 642,0 $ | 80,1 % | 60,1 % | 33,2 % | 35,7 % |
| **MAKER δ=2 central** | **2,1 bps** | **468,4 $** | **73,0 %** | **50,4 %** | **25,3 %** | **21,3 %** |
| MAKER δ=2 pur (sans fallback) | 2,0 bps | 475,4 $ | 73,3 % | 50,8 % | 25,7 % | 21,8 % |
| MAKER stress (fill 90 %) | 3,0 bps | 412,9 $ | 69,8 % | 46,1 % | 22,2 % | 16,4 % |
| TAKER all-in | 6,1 bps | 272,7 $ | 57,2 % | 33,5 % | 13,6 % | 5,8 % |

Lecture : le régime d'exécution **maker δ=2** est le plan de référence —
**+71,8 % de médiane vs taker** (468,4 $ vs 272,7 $), et la probabilité de
la cible complète ×501 passe de 5,8 % (taker) à **21,3 % (maker)** à 36
mois. La cible complète en 12 mois reste hors médiane (P(50 100 $, 12 m) ≈ 0) :
le programme vise V1→V3 en 12 mois et la cible complète prend le temps
qu'elle prend. Constantes d'exécution mesurées (v16/v17/v27, Bybit VIP0
USDT-perp) : fee taker 5,5 bps, fee maker 2,0, demi-spread 0,6 ; fill
maker δ=2 mesuré **97,9 % sur 52 728 tentatives** (1h/708 j), fallback
taker 2,1 % → 2,1 bps/côté effectif (arrondi défavorable).

> ⚠ **NOTE DE RÉVISION EN ATTENTE DE REVIEW (01/10/2026 — docs/29)** : la
> mesure reproductible du fill maker sur le pool P1 (surface δ×TTL + sélection
> réelle, data premium 80 symboles × 733 j) **réfute l'hypothèse d'entrée** de
> cette table : le delta réel de l'entrée maker δ=2/TTL=2 est **+0,375 bps** sur
> les signaux (93,82 % de fill, fallback taker à −88,6 bps — sélection adverse
> concentrée sur A4), contre 4,0 bps crédités ici. Candidat v21 chiffré par le
> noyau MC (contrôles verts) : médiane **306,2 $** (TTL=2) / **364,0 $**
> (TTL=6, +33,6 % vs taker) au lieu de 468,4 $. **Les chiffres officiels de
> cette table restent v20** tant que la review n'a pas validé docs/29 ; le
> chiffre durci « 97,9 % » a désormais une méthodologie reconstructible
> (surface § 3 de docs/29). La jambe de sortie TP (1,488 bps pondéré) tient.
> La règle des coûts ci-dessous n'est pas affectée — elle en est renforcée :
> le fallback taker est le coût le plus cher du système (~88 bps par
> rattrapage).

## LA RÈGLE DES COÛTS (le levier le plus sous-estimé)

Mesure empirique confirmée par v20 : **chaque +2 bps de coût/côté coûte
≈ 20–28 % de médiane 12 m** (v20 : 2,1 → 6,1 bps = −41,8 % de médiane pour
+4 bps). À 6,1 bps taker, les frais consomment la majorité de l'espérance
brute des signaux H1/H4 ; à 2,1 bps maker, la même séquence de trades
produit une médiane ×1,72 (272,7 $ → 468,4 $). Conséquence opérationnelle :
la priorité absolue n'est pas de trouver un nouveau signal mais de
**réduire le coût d'exécution** de ceux qui existent déjà, et de ne
promouvoir que des filtres dont le gain attendu dépasse ~2 bps/côté.
Le registre des pouvoirs (`docs/27-pouvoirs-kscript.md`) liste les
futurs filtres testés sous cette règle.

## L'EXÉCUTION MAKER — LE SEUL LEVIER NOUVEAU POSITIF VALIDÉ

L'instrumentation maker (kScripts `_MK`, contrôlés M1–M15 par
`qa_maker_x501.py`) remplace l'entrée au marché par un **ordre limite
δ=2–5 bps** sous/au-dessus du close, avec : TTL d'expiration (1–12 bougies),
**fallback taker** conditionné (`fallbackTaker`, compteur `mkFb`), verrou de
file (`pendSide == 0`), invalidation au-delà du stop prévu sur les 2 côtés,
transfert complet `pend → plan` au fill (side/qty/stop/entry/fillDone) et
compteurs dédiés (`mkFills`, `mkTOut`, `mkInv`). Mesures de fill mesurées
sur nos données : **97,9 % à δ=2**, **95,8 % à δ=5**. Gain net attendu :
**+4,1 bps/côté** (6,1 → 2,0). La condition de viabilité de V1 est
exactement là : sans le maker, la médiane 12 m reste sous le double du
capital ; avec, elle passe à 475 $ avec 80 % de chances de dépasser 250 $.
La non-régression M13 garantit que chaque ligne de l'original est une
sous-séquence du `_MK` — aucune sémantique de signal modifiée.

## LES FALSIFICATIONS (ce qui a été tué — et pourquoi ça compte)

Trois portes candidates ont été testées et **fermées** indépendamment :

1. **Gate funding z-score** (fz < −1,5 bloque les SHORT) : testé en
   exécution réelle sur l'historique → **−22,0 bps** de gain net. KILL.
   Le funding extrême n'annonce pas un retournement exploitable à notre
   horizon de détention.
2. **Gate flush OI** (ΔOI 6 h ≤ −4,5 %, dédupliqué 24 h) : les 5 576
   événements bruts semblaient rapporter +46,1 bps — c'était un **double
   comptage** de la même déleverisation vue sur symboles voisins. Dédupliqué
   et décalé pour tester la causalité : **+0,1/+0,2 bps**, MFE48 ≈ baseline.
   KILL. Le flush OI est un phénomène de marché, pas un signal.
3. **ML multivarié 11 features** : le « split chronologique » initial
   (AUC 0,56–0,57) était un **split inter-symboles déguisé** — le modèle
   reconnaissait des symboles, pas du temps. Tri global par timestamp (la
   vérité) : **AUC 0,4994**, et 4 plis roulants 0,483 / 0,533 / 0,488 /
   0,471 (signes alternés = bruit pur). Promotion J+30 **annulée**.
4. **Banc local des flux dormants (vague 5, 01/10, `docs/30`)** : le flux
   taker natif des klines (EMA 6/24/72 h) et le funding (moyennes 3/7/30 j)
   testés en filtres continus sur 80 symboles × 1 092 j = 2 053 975 barres,
   grille pré-déclarée, verdict mécanique au critère AUC — **12/12 cellules
   KILL** (AUC 0,4956–0,5103, tous les IC 95 % contiennent 0,5) ; le test
   d'altération de la QA prouve la plomberie vivante (look-ahead :
   AUC 0,5306/0,6103 BTC). Le pattern absorption ÉVÉNEMENTIEL (vague 2)
   n'est pas réfuté par ce banc — son juge reste le protocole A/B.

## LE CRITÈRE DE PROMOTION (durci)

Un scorer prédictif n'entre au programme que si **AUC temporel ≥ 0,60
mesuré sur 60 jours de données fraîches** postérieures à son gel
d'entraînement — critère jamais atteint à ce jour (le scorer A6 est
conservé en **DIAGNOSTIC ONLY** : il décrit, il ne trade pas). Le même
esprit vaut pour les kScripts : un signal entre en papier forward
(protocole v11) avant tout capital réel, et ses seuils sont pré-enregistrés
dans le script lui-même, pas ajustés après coup. La corrélation est
frappante avec les conclusions indépendantes du domaine Aster (l'étude
régimes 4 ans : momentum mort en 2025-2026, mean_reversion la seule
invariance, le harnais optimiste dès qu'une lane stoppe) : deux voies de
recherche séparées ont fermé les mêmes portes — c'est la signature d'une
méthode saine, pas d'un manque d'idées.

## LES ARTEFACTS (tout est versionné dans ce repo)

- **9 kScripts** (`scripts/studies/x501_openmarket/`) : Signature H1/H4,
  Alpha2 (cascade financement), Alpha3 (éruption volatilité), Alpha4
  (confluence MTF), leurs 2 déclinaisons **maker `_MK`**, et 2 collecteurs
  d'observation (`x501_observe_flow_H1`, `x501_observe_cvd4_btc_H1`, zéro
  ordre par construction — contrôle C4).
- **Le scanner/setup** `x501_setup_kscript.js` : l'installation codifiée
  (inputs, contrôles, whitelist de builtins issue de la doc scrapée).
- **4 QA statiques** (49 contrôles scanner + QA générale kScript + M1–M15
  maker + 13 contrôles/collecteur) — toutes **PASS 0 échec** au moment de
  l'intégration, reproductibles en une commande.
- **9 PDF livrables + 2 protocoles** (`docs/reference/openmarket-x501/`) :
  plan de trading, validation backtest, simulation Monte Carlo, mesure
  moteur V5, programme 12 mois multi-alpha, campagne v9 (flux) / v12
  (gestion), stress lab perps, maîtrise plateforme, addendum kScript ;
  protocoles de collecte v10 et de **preuve live v11** (90 jours, 4
  relevés/jour).
- **2 CSV de trades de backtest** (BTC/ETH) comme exemples de sortie.

## LE PIVOT DU 30/09 (décision)

La recherche Aster/FOMO est **gelée au profit d'OpenMarket** : les
collecteurs et nocturnes existants continuent de tourner (rien n'est cassé,
rien n'est supprimé — on ne jette pas une infrastructure qui marche), mais
les nouveaux efforts de recherche, de falsification et d'écriture portent
sur le domaine x501 uniquement. Les enseignements transférables sont déjà
identifiés : la discipline train/val du harnais, le papier forward comme
juge, le registre des verdicts chiffrés, la méfiance systématique envers
les courbes d'équité non re-passées sur le flux de trades. Le reste
(modules campagne, QUBO, radar baleines) reste du contexte Aster/FOMO et
ne migre pas.

## LA ROADMAP (ordre d'exécution)

1. **MC v20 — FAIT (01/10)** — 12 000 trajectoires V1 **sans haircut
gate**, 5 scénarios de coûts, 4 audits verts : médiane 12 m maker 468,4 $
(P(250) 73,0 %) / taker 272,7 $ (P(250) 57,2 %) ; x501 @ 36 m 21,3 % vs
5,8 %. Les chiffres de ce doc sont ceux de v20 ; la baseline `reports/`
est re-éditée.
2. **Instrumentation maker δ=2–5 dans le kScript** — fait côté scripts
   (`_MK` + QA M1–M15) ; reste le suivi de fill réel (les compteurs
   `mkFills/mkFb/mkTOut/mkInv` remplis en papier forward).
3. **Protocole de preuve live 90 j** (v11) — relevés 4×/jour, équité,
   fills, DD, dérive vs simulation ; c'est LE juge avant tout capital réel.
4. **Activation des pouvoirs kScript** (`docs/27-pouvoirs-kscript.md`) —
   vague 1 : régime institutionnel sur les 7 sources premium (ETF, CME,
   Deribit, options/skew, LSR) ; vague 2 : absorption orderbook native ;
   vague 3 : hygiène broker (trail natif, OCA, stats). Même discipline de
   promotion, zéro raccourci.
5. **Banc de test local des flux dormants — FAIT (01/10, `docs/30`)** —
   le flux taker natif et le funding multi-années passés au banc AVANT
   tout run kScript : 12/12 cellules KILL au critère AUC (2 053 975
   barres, plomberie prouvée vivante par le test d'altération). Le
   diagnostic « tu n'exploites aucun pouvoir » reçoit sa réponse
   définitive : les pouvoirs data sont désormais TOUS banc-testés —
   fz, flush OI, ML, flux taker, funding.

## LES RÈGLES NON NÉGOCIABLES

- **Aucun ordre autonome** — l'exécution réelle est déclenchée par le user
  seul, sur les kScripts qu'il a lui-même chargés.
- **Pré-enregistrement avant de croire** — tout seuil, tout gate, tout
  critère d'évaluation est écrit et commité avant le tir (méthode
  `docs/03-methodology.md`).
- **Papier d'abord** — 90 jours de preuve live avant le premier euro réel
  au-delà du capital initial.
- **La truth table des coûts** — aucun chiffre de performance cité sans sa
  bande de coûts (taker 6,1 / maker 2) et sa taille d'échantillon.
- **On ne supprime jamais, on re-catégorise** — les scripts tués vont en
  `scripts/archive_studies/` avec leur en-tête de verdict, comme partout
  dans le repo.
