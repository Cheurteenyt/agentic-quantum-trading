# EXP-holdout-x-2026-10-11 — HOLDOUT-X : les symboles jamais vus du pool v8

**Verdict : FAIL** · gel `745e02d` · moteur `x501_engine_deep_v30.py` (fait foi) ·
jugé sous protocol_v2 · ledger L98.

## La question (spec pré-enregistrée)

L'edge v8 (+0,093 R, n=868, IC95 [−0,027 ; +0,223]) est-il un edge réel mais
mince, ou du sur-apprentissage de SYMBOLE ? Seule épreuve qui sépare les deux :
appliquer les règles TELLES QUELLES à des perps Binance USDT-M jamais présentes
dans SYMS_40.

## Le gel (AVANT toute collecte)

- **Univers figé** : les **48 plus anciennes** perps USDT-M (PERPETUAL, USDT,
  status=TRADING, onboardDate < 2024-01-01) **hors SYMS_40**, lues sur fapi
  exchangeInfo le 11/10, triées par onboardDate croissant. Règle 100 %
  objectivement datée, choisie sans voir une seule barre. Aucun exotique dans
  la tranche (BTCDOMUSDT 52e, USDCUSDT 84e — hors des 48).
- **BTCUSDT au run, hors univers** : ancre de grille + contexte CHOP D1
  (hardcode moteur) ; ses trades exclus du verdict.
- **Protocole** : fenêtre d'analyse < 2026-10-01 (fin base champion) ; 6
  fenêtres protocol_v2 de 2 mois (2025-10-01 → 2026-10-01) ; embargo 72 h en
  zone tampon aux bornes internes ; IC95 = bootstrap blocs-mois 4 000 tirages
  seed 7 ; stress = taker/slip ×1,5, maker TP inchangé.

## Données

Collecte Binance Vision (collecteur v31 champion, `--syms=` sur l'UNION des
deux univers — la DB `om_v27.db` était absente de cette machine) :
**4 388 428 klines 1h / 88 symboles**, **572 224 funding 8h / 88 symboles**
(ts en secondes). QA : 0 NULL taker ; **seule anomalie = le trou ICPUSDT
627 h**, trou RÉEL documenté docs/40 (suspension de trading, vérifié absent
de l'API Binance elle-même).

## Résultats (n=950 trades holdout sur 1 170 bruts)

| Mesure | Holdout (48 jamais vus) | Champion apparié (SYMS_40, MÊME moteur) |
|---|---|---|
| E[R] | **+0,0642** | +0,0731 |
| IC95 blocs-mois | **[−0,0376 ; +0,1793]** | [−0,0255 ; +0,1762] |
| Fenêtres PASS | **3/6** | 4/6 |
| Stress ×1,5 (E[R]) | **+0,0513** | — |
| Hors top 5 % (E[R]) | **−0,1050** | — |

Fenêtres holdout : W1 **−0,374** (n=40) · W2 +0,063 · W3 +0,648 · W4 −0,004 ·
W5 +0,263 · W6 −0,048.

Frais 151,58 $ · funding 2,93 $ · **0 liquidation** · coupe-circuits jour et
semaine actifs (mode mesure).

## Verdict : FAIL (critères pré-enregistrés)

- E[R] > 0 ✓ · n ≥ 400 ✓ · stress ×1,5 tient ✓
- **Borne basse IC95 < 0 ✗** · **3/6 fenêtres < 5/6 ✗**

## La lecture (ce que les données supportent)

Le holdout **ne sépare pas** l'edge du bruit à la barre pré-enregistrée. Mais
le **champion apparié** (même moteur, mêmes fenêtres, mêmes coûts) montre le
**même profil statistique** (+0,073, IC95 couvrant zéro, 4/6). La lecture
« sur-apprentissage de symbole » n'est donc pas la bonne : les symboles jamais
vus se comportent comme les symboles du pool. La lecture correcte est que
**l'edge v8 (+0,093) est resté au-dessous de la barre de preuve protocol_v2**
(borne basse > 0, ≥ 5/6 fenêtres) — le pool v8 n'a jamais eu d'edge ÉTABLI,
le holdout le confirme sur des données vierges.

Le FAIL est un résultat : la question ouverte par docs/40 est fermée, gravée
au ledger (L98) et au registre du domaine (`openmarket_registry.yaml`).
