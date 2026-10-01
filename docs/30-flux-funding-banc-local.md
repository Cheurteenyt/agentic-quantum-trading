# 30 · OPENMARKET — LE BANC DE TEST LOCAL DES FLUX DORMANTS (vague 5)

> **domain: OPENMARKET** · index : [`openmarket/README.md`](openmarket/README.md)
>
> Créé le 01/10/2026. Flux taker natif + funding multi-années mesurés
> (grille pré-déclarée, verdict mécanique). Voir `docs/25`, `docs/29`, `docs/20`.

## LA QUESTION

Deux séries natives jamais utilisées comme signal : (i) **flux taker** klines
(`taker_buy_quote_volume`) (ii) **funding Binance 8h**. Panel : 80 symboles ×
26 208 barres 1h (1 092 j, 0 gap) = **2 053 975 barres**.

## DISCIPLINE (pré-enregistrée)

| famille | score | lookbacks | H | hypothèse |
|---|---|---|---|---|
| A. flux taker | EMA(D,L) D=2·tbqv/qv−1 | L∈{6,24,72} | 24,72 | continuation |
| B. funding | moy. K derniers paiements | K∈{9,21,90} | 24,72 | contrarian |

Verdict AUC domaine : KILL / INCONCLU / CANDIDAT / CONTEXTE (seuils figés script).

## RÉSULTATS

- **Flux taker : 6/6 KILL** (AUC ~0,50–0,504)
- **Funding : 6/6 KILL**
- Pool P1 : INCONCLU (sous gates promotion)

Plomberie prouvée vivante (QA + test look-ahead AUC décolle).

## CE QUE ÇA FERME

Filtres continus flux/funding au panel — **5ᵉ falsification** du domaine.
**Pas clos** : absorption événementielle orderbook (→ `docs/31`, puis A/B).

Re-test = hypothèse **nouvelle** au registre uniquement.

```bash
X501_DATA_DIR=<dir> python3 scripts/studies/x501_openmarket/x501_flux_local.py
X501_DATA_DIR=<dir> python3 scripts/studies/x501_openmarket/qa_flux_local_x501.py
```
