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

## LES CHIFFRES OFFICIELS (config honnête, MC v18 — 12 000 trajectoires)

| Régime | Médiane 12 m | P(≥ 250 $) | Note |
|---|---|---|---|
| V1 taker (S3, ~6,1 bps/côté) | **216 $** | — | le plan de base à frais taker |
| **V1 maker (δ=2, ~2 bps/côté)** | **475 $** | **80 %** | **le plan de référence actuel** |
| V2 (empilement 2 alphas) | 1 012 $ | 92,5 % | nécessite V1 viable |
| V3 (3 alphas, DD mesuré 22,09 %) | 2 353 $ | 98,7 % | sous la borne DD 25 % |
| V4 (borne sup « parfaite ») | 38 991 $ | — | **PAS un plan** — plafond théorique |
| V5 (stress défavorable) | 215,7 $ | — | le plan survit au stress |

La cible ×501 complète (les 50 100 $) est atteinte dans **96,5 % des
trajectoires à 36 mois** : en 12 mois le programme vise la médiane V1/V3,
la trajectoire complète prend le temps qu'elle prend. Aucun de ces chiffres
n'est une promesse : ce sont des médianes de simulation Monte Carlo sous
bandes de coûts explicites (taker 6,1 bps, maker 2 bps), avec les slippages
et les gaps pessimistes du harnais. Le régime V4 est affiché uniquement
pour borner le modèle ; croire à V4 serait la même erreur que croire aux
sharpe OOS du harnais optimiste (cf. le bug T7 du domaine Aster).

## LA RÈGLE DES COÛTS (le levier le plus sous-estimé)

Mesure empirique de la v18 : **chaque −2 bps de coût/côté ≈ +25 % de médiane
12 m** sur l'horizon de la mission. À 6,1 bps taker, les frais consomment la
majorité de l'espérance brute des signaux H1/H4 ; à 2 bps maker, la même
séquence de trades produit une médiane ×2,2 (216 $ → 475 $). Conséquence
opérationnelle : la priorité absolue n'est pas de trouver un nouveau signal
mais de **réduire le coût d'exécution** de ceux qui existent déjà. Toute
nouvelle variante de signal qui n'améliore pas le net-after-cost de plus de
~2 bps/côté est indistinguible du bruit à cet horizon — autant ne pas la
promouvoir.

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

1. **MC v20** — re-simulation 12 000 trajectoires du régime V1 **sans
   haircut gate** (le gate forçait la sortie au pire moment), sous les deux
   bandes de coûts {taker 6,1 ; maker 2} → médiane 12 m + P(250 $) par
   régime. C'est la mise à jour officielle attendue de la table ci-dessus.
2. **Instrumentation maker δ=2–5 dans le kScript** — fait côté scripts
   (`_MK` + QA M1–M15) ; reste le suivi de fill réel (les compteurs
   `mkFills/mkFb/mkTOut/mkInv` remplis en papier forward).
3. **Protocole de preuve live 90 j** (v11) — relevés 4×/jour, équité,
   fills, DD, dérive vs simulation ; c'est LE juge avant tout capital réel.
4. **MC v20 → table officielle mise à jour** dans ce doc + baseline
   `reports/` rafraîchie.

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
