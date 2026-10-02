# INV-C « L'ÉCHO DE LIQUIDATION » — PRÉ-ENREGISTREMENT (02/10/2026, AVANT toute mesure)

Statut : **EXPERIMENTAL forward-only** — gouvernance docs/38, tag freeze-2026-10-02,
budget consommé : 1 expérience (famille forced-flow). La donnée n'existe pas encore
pour un backtest (liq_events : 10 jours au 02/10, 4 838 événements ; OI : 3-7 j) —
cette expérience est donc pré-enregistrée MAINTENANT et jugée quand n suffira.

## La construction (jamais existée)

1. **Burst** : une heure où le notional total liquidé d'un symbole dépasse le
   quantile 95 des heures à liquidation de la FENÊTRE DE CALIBRATION (les 30
   premiers jours de collecte au moment du gel du seuil — le seuil est calculé
   UNE fois, gelé, écrit ici en amendment, jamais retuné).
2. **Réponse** (les 6 bougies 1h suivantes, via le flux agressif net des klines
   buy/sell volume) : le flux net signé et le prix.
3. **Classification ex-ante à la 6ᵉ bougie** (avant de connaître le futur) :
   - CONTINUATION : flux net même signe que le burst ET prix qui prolonge ;
   - ABSORPTION : flux net opposé ET prix qui tient (±0,5 % du prix burst) ;
   - EXHAUSTION : flux net opposé ET prix qui prolonge quand même.

## L'hypothèse falsifiable (pré-déclarée)

**La CLASSE de réponse (pas la taille du burst) prédit le mouvement 24h** :
continuation → continuation edge ; exhaustion → fade edge ; absorption → neutre.
Interdiction §36 de l'audit : aucun « grosse liq → short » ou « → long » simple —
le signal est DANS la réponse post-flux, jamais dans le burst seul.

## PASS/FAIL écrits avant

- PASS : espérance nette par classe > 0 en calibration ET en fenêtre de validation
  temporelle distincte (split à la date du gel), contrôle inverse battu (la classe
  opposée doit être pire), n ≥ 30 bursts par classe testée.
- FAIL : tout le reste — gravé, budget consommé, STOP.

## Garde-fous

1x (jamais de levier en signal brut), coûts 18 bps RT, BLOC STATS mensuel,
verdict doctrine NUL/CONTEXTE/CANDIDATE, coordination : distinct des tirs
OI H4/H5 (06-07/10 — le quadrant OI×prix ; ici la variable = la réponse de flux
post-liq). Les résultats au registre research/registry.yaml + docs/20.
