# Token Market Candidate Acquisition Source Plan - Read-Only

## Purpose

This plan pauses Core Equity before any real CEX label write and defines how to identify 2-3 additional token-market candidates safely.

The goal is not to create labels. The goal is to decide what would qualify as a clean candidate before sending anything through the review-first pipeline.

## Simple Status

- `LAB` is the only complete token-market candidate currently validated in local Core Equity state.
- `LAB` reached the final CEX label write safety checkpoint, but the real label button remains off.
- Local raw data exists, including pair tokens and token transfers, but those rows are only clues.
- Raw local clues are not candidates until they have a reviewed source, source tier, stable digest, and clear CEX/DEX route.
- The final CEX label table still does not exist, and no CEX label has been written.

## Candidate Eligibility

A candidate can enter the next review-first path only if all of these are present:

- `token_symbol`
- `market_type`
- clear route: `cex`, `dex`, or `manual_review`
- source URL
- source tier: preferably `tier_1` or `tier_2`
- evidence type
- stable evidence preview or digest
- source policy
- no duplicate dedupe key
- no parent-chain break
- no source/digest/JSON drift if it already came from an existing contract

## Allowed Sources

Allowed by default:

- RAG memory
- project docs
- existing local DB rows read-only
- existing dry-run/review queue outputs
- manually supplied source URLs from the product owner
- exported read-only reports copied into memory

Not allowed by default:

- provider calls
- scraping
- browser harvesting
- credentials or API keys
- runtime writes
- DB writes
- migrations
- status updates
- automatic candidate insertion

## Candidate Lanes

### Lane A - Existing Validated Candidate

`LAB` is valid as the reference candidate:

- route: CEX
- venue/source: Gate market evidence
- source tier: `tier_1`
- digest: present
- state: final safety checkpoint ready-but-disabled
- action: keep as reference, do not write label yet

### Lane B - Local Raw Leads

Local raw observations can be used only as leads:

- `pair_tokens`
- `token_transfers`
- swap-derived token appearances
- CEX deposit/funding graph hints

These are blocked as candidates until a source URL, source tier, evidence type, digest, and route are attached.

### Lane C - Manual Source Intake

The safest next acquisition method is manual intake:

- the user/admin provides 2-3 token/source pairs
- Codex validates them in read-only mode
- each proposed candidate gets a route classification
- unclear/hybrid cases stay manual review
- no candidate row is inserted until a later confirmed dry-run-first goal

## CEX/DEX Route Separation

- CEX candidates may go only toward CEX review queues.
- CEX candidates must never create a direct CEX label.
- DEX candidates may go only toward DEX/router review paths.
- DEX candidates must never create a direct mapping.
- Hybrid, aggregator, perp, unknown, or unclear cases stay blocked/manual.
- No candidate route may connect to trade execution, wallet orders, client signals, or opt-ins.

## Blockers

Block a proposed candidate if:

- source URL is missing
- source tier is missing or weak
- evidence type is missing
- digest is missing or unstable
- token symbol is ambiguous
- CEX/DEX route is unclear
- parent chain is not available
- JSON/source binding drifts
- duplicate dedupe key is found
- candidate depends on provider/scraping not explicitly approved
- candidate would imply a label, mapping, trade, signal, or opt-in

## Validation Checklist

- 2-3 proposed candidates listed, or blockers explained.
- Each candidate has source URL, source tier, evidence type, digest/preview, and route.
- `LAB` remains the only already complete reference candidate unless new candidates are manually supplied or explicitly sourced.
- `would_write=false`.
- `writes_performed=0`.
- No DB table is created.
- No row is inserted.
- No status is updated.
- No CEX label is created.
- No final label table is created or mutated.
- No DEX router evidence is created.
- No mapping, trade, wallet order, client signal, or client opt-in is created.

## Sidecar Review

Spark/Hubble confirmed the safe gates:

- use local/RAG data only by default
- require source URL, source tier, evidence type, stable digest, token symbol, market type, and route classification
- keep CEX and DEX paths separate
- keep hybrid/unclear cases manual or blocked
- keep providers, scraping, writes, labels, mappings, trades, signals, and opt-ins disabled

## Recommended Next Goal

```text
/goal Continue Core Equity en mode economique, priorite token market manual candidate intake contract read-only.

Objectif:
Creer un contrat read-only pour recevoir plus tard 2-3 candidats token-market fournis manuellement, sans les inserer en DB.

Pourquoi:
Le plan source montre qu'on n'a pas assez de candidats propres en local.
La methode la plus sure est de permettre une fiche d'entree manuelle qui exige source, tier, digest et route avant toute future insertion.

Garde-fous:
- read-only
- aucun DB write
- aucune row candidate inseree
- aucun provider/scraping
- aucun label CEX
- aucun router evidence DEX
- aucun mapping
- aucun trade
- aucun opt-in client

Validation:
- accepte seulement un preview de candidats
- bloque les candidats sans source/tier/digest/route
- classe CEX/DEX/manual
- would_write=false
- writes_performed=0
- DB metier inchangee
```
