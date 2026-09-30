# 31 · OPENMARKET — LE BANC D'ÉVÉNEMENTS DE L'ABSORPTION (vague 6)

> Créé le 01/10/2026. La structure événementielle passe au banc en proxy
> klines, AVANT que le user dépense les 2 runs ABS de la plateforme — la
> suite exacte de `docs/30` (la vague 5 avait fermé les filtres continus et
> désigné le pattern événementiel comme LA voie ouverte). Étude :
> `scripts/studies/x501_openmarket/x501_abs_events_local.py` +
> `abs_events_local.json` (reproductible bit à bit, 173 s). QA :
> `qa_abs_events_x501.py` — 9 familles, 62 contrôles, 0 échec.

## LA QUESTION (dimensionnée AVANT les runs ABS)

Le protocole A/B (`docs/28`, runs 3-4) fait de l'absorption orderbook un
test plateforme à N_MIN = 12. La vague 5 a laissé cette porte ouverte mais
n'a rien dit de sa TAILLE : combien d'événements existent (le run sera-t-il
DATA_ABSENTE par construction ?), quelle taille d'effet attendre, et — la
question la plus chère — **la structure à 4 conditions ajoute-t-elle
quelque chose face à la simple attaque ?** La leçon du registre Aster
(« la dynamique bat la moyenne ») prédit qu'OUI ; le banc la teste
gratuitement, en proxy klines, sur l'univers complet : **80 symboles ×
2 053 975 barres 1h (01/10/2023 → 27/10/2026, 0 gap)** — 3 minutes de CPU
locale contre 2 backtests de plateforme.

## LA DISCIPLINE (pré-enregistrée avant la première mesure)

L'événement est la séquence ordonnée de la vague 2, transposée klines avec
les invariants réels (tbqv ≤ qv, D ∈ [−1, 1]) : **MUR** à T−3 (volume ≥ 3×
SMA200), **ATTAQUE** directionnelle à T−2 (vague taker ≥ 2× SMA100 de la
même série), **TENUE** à T−1 (l'extrême de l'attaque tient à 0,8 %),
**REPRISE** à T−1 (EMA(D, 6) bascule côté mur) — décision à l'OPEN de T,
entrée doctrine _MK. Trois définitions IMBRIQUées, pré-déclarées :
**E1** = attaque seule (la « moyenne » de référence) ; **E2** = attaque +
tenue + reprise (la structure sans le mur) ; **E3** = mur + attaque + tenue
+ reprise (l'ombre klines du pattern plateforme). La grille complète :
3 définitions × 2 directions × 2 horizons {24, 72} = 12 cellules de panel
au critère AUC du domaine (Mann-Whitney événement vs non-événement, IC 95 %
bootstrap par journées UTC seed 501, seuils inchangés : KILL < 0,02,
CANDIDAT ≥ 0,05) + 4 cellules de **prime de structure** (delta des médianes
E3 − E1, bootstrap 10 000, seuil pré-déclaré : IC exclut 0 ET delta ≥
+6 bps = la moitié de la bande aller-retour taker ET n_E3 ≥ 12) + la
projection sur le pool P1 (CONTEXTE). La règle de lecture de la masse
d'ex-aequo est pré-déclarée : une jambe de prime à médiane 0,0 avec ≥ 50 %
de zéros exacts est NON_INTERPRETABLE (la médiane est dans les liens).

## LES RÉSULTATS (abs_events_local.json, reproductible bit à bit)

**1. La prime de structure est RÉFUTÉE — 0/4 cellules.** Côté LONG :
E3 − E1 = **−26,4 bps** à H24 (P(delta > 0) = 0,069) et **−54,2 bps** à H72
(P = 0,038) — la structure ne fait pas juste « ne rien ajouter », elle
SOUSTRAIT, avec un IC qui fuit vers le bas. Côté SHORT : les 2 cellules sont
NON_INTERPRETABLES (médianes dans la masse des zéros, voir §3) — le verdict
reste ABS_DEPRIORISE, les conditions du JUSTIFIE n'étant pas réunies.

**2. Chaque condition de confirmation DÉGRADE le signal LONG.** L'AUC
d'événement descend en cascade : E1 0,5114 (H24) → E2 0,5033 (KILL) → E3
0,4943 (KILL) ; à H72 : 0,5172 → 0,5052 → 0,4957. L'attaque seule est
INCONCLUE (IC H72 [0,5081, 0,5306] exclut 0,5, séparation 0,0172 < 0,05)
avec +34,1 bps de médiane — le mécanisme continuation existe — mais la
confirmation le DÉPENSE : le rebond se joue DANS la barre de tenue, et à
l'open de décision l'absorption est déjà payée. **La structure
confirmatoire est TARDIVE, pas fausse** — c'est la version événementielle de
la leçon de la vague 5 (les moyennes lavez les spikes ; ici, les
confirmations ratent le spike).

**3. Le miroir SHORT est ANTI-ABSORPTION (CONTEXTE, 6/6 cellules).** Toutes
les cellules SHORT ont AUC < 0,5 (0,4767 à 0,4886) : les attaques
acheteuses « absorbées » en haut précèdent la CONTINUATION haussière — le
mur perd, la dynamique le traverse. C'est exactement l'asymétrie breakout
documentée sur le pool P1 (médiane R −0,319, WR faible, RR élevé) et la
leçon registre Aster. La question « mur vendeur tenu = short ? » reçoit la
réponse contraire en ombre klines.

**4. Le proxy klines du mur SÉLECTIONNE LA PLAINE ILLIQUIDE.** 62,7 % des
événements E3 SHORT ont un rendement forward EXACTEMENT nul à H24 (opens
répétés des microcaps, la pathologie documentée vague 5) contre 18,9 % des
E1 : sans le contexte carnet, « volume ≥ 3× SMA200 » est un aimant à
plaine plate où rien ne bouge — le mur de VOLUME n'est pas un mur de
CARNET. C'est la limite L1 en chair : le banc ne mesure pas maxBidAmount,
il mesure ce qu'il en reste dans les klines.

**5. Les événements existent — les runs ABS ne seront pas DATA_ABSENTE.**
Focus plateforme : BTC 278 E3 LONG / 351 E3 SHORT, ETH 204 / 334 sur la
fenêtre ; l'univers complet 11 018 E3 LONG / 63 586 E3 SHORT (croissance
2023 → 2026 : 3 283 → 30 358/an, l'univers s'élargit). La projection sur le
pool P1 : **12/469 entrées matchées**, delta +0,13 R, P(bootstrap) = 0,652 —
INCONCLU au moteur (sous le gate 0,70), aucun argument de promotion.

## LA DÉCISION (pré-déclarée, appliquée mécaniquement)

**ABS_DEPRIORISE — les runs 3-4 (ABS) passent DERRIÈRE les runs RI (1-2) et
MK6 (7-8) dans la file du user.** Le protocole `docs/28` reste LE juge de
l'ordrebook : ce banc ne l'a pas réfuté, il a SIZÉ l'attente. Et il rend le
test ABS plus informatif qu'avant : si la version orderbook réelle
(maxBidAmount) produit un verdict positif là où son ombre klines est morte,
la preuve que le champ carnet porte une information UNIQUE sera faite par
contraste ; si l'ABS est mort aussi, le pattern est clos des deux côtés
(6e falsification étendue). Dans les deux cas, le user sait maintenant
pourquoi le run vaut (ou ne vaut pas) sa place dans la file.

## CE QUE ÇA FERME — ET CE QUE ÇA NE FERME PAS

**Clos en ombre klines** : le pattern absorption à 4 conditions SANS champ
orderbook (la seule chose que les données locales pouvaient tester) — la
prime de structure est négative côté LONG, anti-signal côté SHORT, et le
proxy du mur selectionne l'illiquide. Aucune variante klines de
l'absorption ne rentrera dans un kScript sur cette base.

**Pas clos** : le pattern orderbook RÉEL (maxBidAmount à depthPct 1 %) —
juge : runs 3-4 du protocole A/B, désormais en queue de file. La voie data
est elle-même close dans son ensemble : les pouvoirs du domaine sont
tous banc-testés (fz −22,0 bps, flush OI +0,1/+0,2 bps, ML AUC 0,4994,
flux + funding 12/12 KILL, absorption-proxy 0/4) — **la 6e falsification du
domaine est aussi la première qui PRIORISE la file de runs du user au lieu
d'ouvrir une piste**.

## REPRODUCTION

```bash
X501_DATA_DIR=<dir des {SYM}_1h.csv> \
    python3 scripts/studies/x501_openmarket/x501_abs_events_local.py
X501_DATA_DIR=<dir> python3 scripts/studies/x501_openmarket/qa_abs_events_x501.py
```

Limites pré-enregistrées (L1-L5, en-tête du script) : mur de VOLUME, pas de
CARNET (L1) ; reprise D ≥ 0 plus faible que le déséquilibre orderbook ≥ 1,2
→ le pool local est une borne haute (L2) ; flux Binance, pas openmarket (L3)
; bootstrap réduit déterministe 50 000 points/cellule, AUC ponctuelle
full-sample (L4) ; horizons en barres (L5). Bande de coûts de lecture :
taker 6,1 bps/côté, maker 2 bps/côté — le seuil de la prime (+6 bps) est la
moitié de l'aller-retour taker 12,2 bps.
