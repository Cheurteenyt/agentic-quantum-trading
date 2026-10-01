# 28 · OPENMARKET — LE PROTOCOLE A/B PRÉ-ENREGISTRÉ (vagues 1-2)

> **domain: OPENMARKET** · index : [`openmarket/README.md`](openmarket/README.md)
>
> Créé le 01/10/2026, **AVANT** tout run A/B — critères figés ici.
> Moteur : `scripts/studies/x501_openmarket/x501_verdict_ab.py` (seed 501).
> Registre : `docs/20`. Plan pouvoirs : `docs/27`.
>
> **File de runs (vague 6, docs/31)** : **RI (1-2) → MK6 (7-8) → TRAIL (5-6) → ABS (3-4)**.

## LA RÈGLE

Rien ne touche la config officielle (MC v20) sans verdict **PROMOTION** de ce protocole.
KILL / INCONCLU → référence intacte.

## LES 8 RUNS

| # | test | A (contrôle) | B (traitement) | symbole | N_MIN |
|---|---|---|---|---|---|
| 1 | RI-BTC | Signature_H1 | Signature_H1_RI | BTCUSDT 1h | 20 |
| 2 | RI-ETH | idem | idem | ETHUSDT 1h | 20 |
| 3 | ABS-BTC | Signature_H1 | Absorption_H1 | BTCUSDT 1h | 12 |
| 4 | ABS-ETH | idem | idem | ETHUSDT 1h | 12 |
| 5–6 | TRAIL (opt.) | `_MK` trail=false | trail=true | BTC/ETH | 20 |
| 7–8 | MK6 | `_MK` TTL=2 | TTL=6 | BTC/ETH | 20 |

CSV : `scripts/studies/x501_openmarket/ab/ab_x501_<sym>_<setup>_<on|off>.csv`

```bash
python3 x501_verdict_ab.py ab_x501_BTCUSDT_ri_off.csv ab_x501_BTCUSDT_ri_on.csv --label "RI-BTC"
```

## CRITÈRES (ordre strict)

1. **DATA_ABSENTE** — n_B ≥ 97 % de n_A (filtre transparent / data morte)
2. **PROMOTION** — n_B ≥ N_MIN ET P(méd_B > méd_A) ≥ 0,70 ET Δméd ≥ +0,10 R ET maxDD_B ≤ maxDD_A + 2 R
3. **KILL** — P ≤ 0,40 ET n_B ≥ 10
4. **INCONCLU** — le reste (souvent n_B < N_MIN au 1er run → élargir fenêtre, **jamais** promouvoir sous N_MIN)

## PIÈGES PRÉ-ENREGISTRÉS

- Fail-open RI si < 3/5 composantes
- Saturation ETF `htf` possible → corriger projection, re-run
- ABS = fenêtre orderbook limitée → PROMOTION = CANDIDAT papier v11 seulement
- OCA par tranche ; trail natif défaut false (MC v20 bit-à-bit)

## APRÈS VERDICT

| Verdict | Action |
|---|---|
| PROMOTION | CANDIDAT registre + paper |
| KILL | NUL registre |
| INCONCLU | fenêtre / accumulation |
| DATA_ABSENTE | réparer observe, re-run |
