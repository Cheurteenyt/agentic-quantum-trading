# LE LEDGER DE PREUVES — Research Firewall, couches 1 et 3

Le firewall (audit GPT v3 §26-27) : le modèle est libre de penser, proposer
et expérimenter — mais il n'est **jamais l'autorité de vérité**. La vérité =
la chaîne hypothèse → code → exécution → résultat → vérification → evidence →
ledger → STATE.

## Le format (facts.jsonl, une ligne = un fait)

```json
{"id": "F-001", "date": "2026-10-05", "sha": "bff4f29",
 "path": "backend/services/backtest_v2/gates.py",
 "claim": "F1 : le Sharpe V2 est annualisé à la fréquence réelle des barres",
 "status": "fixed",
 "require_present": ["def bars_per_year", "periods_per_year"],
 "require_absent": [],
 "evidence": ["PR #100", "tests/test_lot1_sharpe_frequency.py"],
 "source": "audit GPT v1 F1"}
```

- `status` : `fixed` (un bug, corrigé) · `confirmed` (un fait vérifié) ·
  `refuted` (un claim jamais vrai — il ne faut plus le re-tester) ·
  `stale` (une mesure historique supplantée — l'ABSOLUS pré-fix) ·
  `context` (contexte non vérifiable mécaniquement).
- `require_present` / `require_absent` : les patterns que `claim_verify.py`
  cherche dans `path` pour juger le fait SUR LE CONTENU, pas sur le souvenir.
- `evidence` : les preuves (PR, tests, rapports) — un fait sans preuve est
  une opinion.

## Les règles du firewall

1. **UNVERIFIED / CONTRADICTED n'entre jamais dans STATE.md** — un fait
   contredit se corrige dans le ledger (status + patterns) ou se réfute, via
   une PR.
2. Toute affirmation d'un agent porte son `id` de fait ou sa commande de
   reproduction — un chiffre sans preuve est présumé halluciné (règle docs/39
   §0.6, généralisée).
3. On n'ajoute pas de fait « améliorable » : le ledger tient des faits
   vérifiables, pas des opinions.

## Usage

```bash
python scripts/claim_verify.py --all      # revérifie tout (exit 1 si contredit)
python scripts/claim_verify.py --id F-018 # un fait
python scripts/claim_verify.py --stats    # comptage par statut
python scripts/context_manifest.py        # LE brief d'entrée d'une session
```
