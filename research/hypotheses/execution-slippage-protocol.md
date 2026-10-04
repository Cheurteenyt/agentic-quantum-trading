# PROTOCOLE PRÉ-ENREGISTRÉ — le coût d'exécution humaine (scellé le 03/10, AVANT toute mesure de kill)

Origine : le flag du tournoi Bonsai du 03/10 (« sans mesure réelle du coût d'exécution,
aucun backtest n'est valide ») — vérifié exact : `slippage_measured` = 6 lignes orphelines.
Conception : Bonsai (métriques + seuils, dérivés de la théorie, PAS de nos données) ;
mesures et vérifications : l'agent. Sondage source : `scripts/studies/execution_slippage_probe.py`.

## L'état des données (constaté 03/10)

- `aster_tape` = **BTCUSDT + ETHUSDT uniquement** (11,6 M prints) → le slippage des flux
  meme/survivor/listing est **inmesurable** aujourd'hui.
- `depth.db` couvre 15/36 symboles des paper trades (half-spread = le plancher taker, proxy).
- Les champs signal_ts/entry_ts du ledger sont **pollués** (2 conventions : 0 s et exactement
  3600 s, n=59) → la latence humaine n'est PAS mesurable depuis le ledger ; ne jamais s'en servir.

## Les métriques (gelées)

1. **Pire-30s** (FAIT FOI) : S = max sur [entry_ts, entry_ts+30 s] de dir×(P_t/open − 1), en bps.
   La fenêtre absorbe la latence humaine (1-5 s) et le micro-drift post-open.
2. Taker-immédiat : dir×(premier_print/open − 1) — le plancher.
3. VWAP-60s : dir×(vwap_60s/open − 1) — le diagnostic de passivité.

## Les seuils KILL (pré-enregistrés, théorie adversariale — invalidation du flux si dépassés)

| Flux | Edge net/trade | Seuil pire-30s | Notional de référence |
|---|---|---|---|
| Cascade majors 12x | 10-20 bps | **15 bps** | 50 $ |
| Meme fade 1x | 5-10 bps | **8 bps** | 20 $ |
| Vol_spike 1x | ~10 bps | **10 bps** | 30 $ |
| Survivor LONG 1x | ~9 bps | **7 bps** | 25 $ |
| Listing-fade (si validé lun 05/10) | ~9 bps | **9 bps** | 10 $ |

Règle : slippage_moyen/edge_net > 1 sur 20 trades → backtests du flux INVALIDÉS à ce notional.

## Les bornes (ce que la tape ne peut pas dire)

- Position dans la file : bornée au premier print après entry_ts (hypothèse conservatrice).
- Fills partiels : assumés 100 % à la métrique (le notional 10-50 $ est sous le size médian des prints majors).
- Latence humaine : absorbée par la fenêtre pire-30s ; jamais estimée depuis le ledger (pollué).

## Les premières mesures (03/10, descriptives — PAS des kills)

Majors, n=30 trades sur tape réelle : taker-immédiat ≈ 0 bps (médiane), pire-30s médiane
+1,8 / p90 **+7,5** / max +19,1 bps → **PASS vs le seuil 15 bps**. L'hypothèse open = fill
tient sur le profond ; la queue à 19 bps justifie le seuil (un trade sur ~30 le touche).

## La suite (hors budget, décision utilisateur)

1. Étendre le collecteur tape aux symboles des flux meme/vol_spike/survivor (~40 symboles)
   — LE prérequis pour mesurer les flux à risque ; proposition pour lun 05/10.
2. En attendant : le half-spread depth (15/36 syms) = plancher taker par trade, mesurable
   par la même sonde (mode --depth à écrire si la décision passe).
3. Re-mesure : avec la revue hebdo du paper forward ; la table `slippage_measured` v2
   (symbol, ts, flux, notional, taker_bps, worst30_bps, vwap60_bps, n_prints, captured_at).

## LA MESURE DE PLANCHER (03/10 nuit, execution_depth_floor.py — la section qui change la semaine)

Le spread du carnet RÉEL aux moments d'entry (depth.db, 102 M bins, un scan joint, n=301) :

| Classe | Spread médian | p90 | Verdict vs seuil/2 du protocole |
|---|---|---|---|
| Majors (BTC/ETH/ASTER) | 0-2 bps | 2 bps | intenable ? NON — le plancher tient |
| WIF/PNUT/TURBO/TRUMP/PONS (13-20 bps méd) | 16 bps | ~26 | **au-dessus de meme 8/2 = 4 bps** |
| BOME/DOGS/FARTCOIN/MOODENG/NEIRO (16-24 bps) | 18 bps | ~30 | idem |
| CATEUSDT / MEMEUSDT | **152 / 200 bps** | 388 / 390 | hors d'atteinte |

**L'IMPLICATION (descriptive, le kill formel passe par la règle des 20 trades)** : les flux
meme/vol_spike assument 8 bps RT — le plancher de spread réel de LEUR univers est 12-24 bps
médian (taker = traverser le spread). Le coût d'exécution réel est 2-3× l'hypothèse sur les
meilleurs symboles du flux, 25× sur CATE/MEME. La décision lundi : re-coster les flux meme
avec le spread réel par symbole (1 créneau du budget — la mutation de coût est pré-enregistrée
ICI avant le run) et étendre le collecteur tape. Les flux majors/survivor (0-2 bps) ne sont
pas concernés.

## Les propositions novembre de Bonsai (03/10 nuit — le filtre de l'agent)

1. « Léchérie de la liquidation » → **REJET** : duplique INV-C (déjà armée, verdict mi-nov)
   et split « janv-déc 2022 » = des données qui n'existent pas (liq WS depuis sept 2026).
2. « Cascades de listings » → **REJET** : « acheter la volatilité » = pas d'instrument
   (pas d'options sur Aster) ; l'observation est trivialement connue, pas un edge.
Bonsai 0/2 — mode d'échec constant : mécanisme plausible, données fabriquées, action non
exécutable. L'archive : reports/aster/bonsai-novembre-propositions-2026-10-03.md.

## CORRECTION DE RÉFÉRENTIEL + LE VERDICT DU RE-COST (04/10)

**La correction** (avant le run, exigence d'honnêteté) : le RT assumé de la MACHINE est
TAKER_RT = **28 bps** ((4 frais + 10 slippage) × 2) — le « 8 bps » de la section ci-dessus
était le coût du backtest premium-fade, PAS l'hypothèse du flux meme. Le plancher de spread
mesuré (12-24 bps médian) s'additionne aux frais : RT réel ≈ spread + 8 = 20-32 bps —
**l'hypothèse des 28 couvrait le spread médian mesuré**. La section précédente surestimait
le risque d'un facteur 2-3 sur la médiane ; il ne subsiste vrai que pour la queue fine
(CATE 160, MEME 208, NEIRO-tail RT réels).

**Le verdict du re-cost** (volspike_recost_spread.py, ledger PASS — la mutation de coût
pré-enregistrée) : le flux vol_spike_meme FROZEN **tient au coût réel par symbole** —
espérance +0,0138 → +0,0161 $/trade (Δ +17,2 %, le réel est légèrement PLUS favorable :
le fallback 24 bps < 28 assumés sur la médiane), 897 trades séquentiels, 0 liq. Seuls
2,3 % des events (NEIRO/BOME/DOGS/CATE/MEME) dépassent l'hypothèse — absorbés. La question
maker (récupérer le spread si fill) reste ouverte mais n'est plus urgente : le taker tient.
