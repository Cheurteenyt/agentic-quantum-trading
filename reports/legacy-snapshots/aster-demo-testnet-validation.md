# Aster Demo/Testnet Validation

## Objectif

Valider que notre forward paper n'est pas une simulation de confort avant toute execution reelle.

La sequence de validation reste:

1. Backtest historique sur donnees publiques.
2. Forward paper interne avec ledger SQLite.
3. Comparaison forward vs marche public recent.
4. Demo/testnet Aster en lecture seule.
5. Plus tard seulement: validation d'ordres fictifs/demos, jamais de fonds reels par defaut.

## Endpoint ajoute

`/api/onchain/rpc/aster-demo-testnet-readiness-preview`

Ce preview:

- teste les endpoints publics futures V3 testnet;
- compare un book ticker testnet au ticker mainnet de reference;
- verifie uniquement la presence des variables d'environnement testnet;
- peut tester `GET /fapi/v3/balance` si `include_signed_readonly_probe=true`;
- ne place aucun ordre;
- ne cree aucune transaction wallet;
- ne persiste rien.

Variables optionnelles:

- `ASTER_TESTNET_API_KEY`
- `ASTER_TESTNET_API_SECRET`

## Garde-fous

- `dry_run=true` obligatoire.
- Pas de `POST /fapi/v3/order`.
- Pas de changement de leverage, marge ou position mode.
- Pas de transfert.
- Pas de signature d'ordre.
- Les balances sont reduites a des flags de presence; les credentials ne sont jamais retournes.

## Pourquoi c'est important

Notre forward paper peut prouver que la logique se comporte bien sur les trades publics recents, mais il ne prouve pas:

- que l'ordre serait accepte par Aster;
- que le symbole est autorise sur le compte;
- que les filtres `LOT_SIZE`, `MIN_NOTIONAL`, `PRICE_FILTER` passent;
- que la marge et le leverage sont disponibles;
- que l'execution ne serait pas rejetee.

Le testnet/demo sert a combler exactement ce trou, sans argent reel.

## Resultat du 2026-06-01

Le testnet Aster est maintenant valide en lecture signee:

- REST public testnet OK: `ping`, `time`, `exchangeInfo`, `bookTicker`.
- Agent wallet dedie cree localement puis autorise sur Aster Testnet.
- Signature EIP-712 OK avec `ASTER_TESTNET_AGENT_PRIVATE_KEY`.
- `GET /fapi/v3/balance` OK en read-only.
- Assets vus en lecture: `BTC`, `ASTER`, `USDT`, `AFEE`.
- Aucune transaction, aucun ordre, aucun write DB.

Variables utilisees:

- `ASTER_TESTNET_USER_ADDRESS`
- `ASTER_TESTNET_AGENT_ADDRESS`
- `ASTER_TESTNET_AGENT_PRIVATE_KEY`

Important: l'agent wallet Aster affiche une adresse publique et des permissions,
mais pas la private key. Pour signer cote backend, nous avons donc cree un wallet
agent dedie dont nous possedons la private key, puis nous avons autorise son
adresse via l'interface Aster Testnet.

## Order intent validator

Endpoint ajoute:

`/api/onchain/rpc/aster-demo-order-intent-validator-preview`

Ce validateur ne place pas d'ordre. Il prepare seulement une intention d'ordre
et verifie:

- presence du symbole dans `exchangeInfo` testnet;
- `bookTicker` testnet;
- `tickSize`;
- `stepSize`;
- `minQty`;
- `minNotional`;
- prix/quantite arrondis;
- notional estime apres arrondi.

Smoke test:

- `BTCUSDT`, 50 USDT: bloque, quantite arrondie a zero / sous min notional.
- `BTCUSDT`, 100 USDT: intention d'ordre valide.
- `BTCUSDT`, 500 USDT: intention d'ordre valide.
- `BTCUSDT`, 1000 USDT: intention d'ordre valide.

Verdict pratique: le validateur fonctionne, mais le testnet ne liste pas nos
champions actuels:

- `LABUSDT`: absent du testnet;
- `INJUSDT`: absent du testnet;
- `TIAUSDT`: absent du testnet;
- `INTCUSDT`: absent du testnet.

Conclusion: le testnet Aster est utile pour valider la mecanique de signature,
les filtres d'ordre et les tailles minimales, mais il ne valide pas directement
les lanes championnes si ces symboles ne sont pas disponibles sur testnet.

## Decision actuelle

On ne doit pas passer du temps a forcer le testnet sur `LABUSDT/INJUSDT/TIAUSDT/INTCUSDT`.
Le testnet reste un outil de validation d'execution generique, pas le moteur de
selection strategique.

Priorite suivante:

1. Continuer les backtests/forward sur mainnet public read-only pour les vrais symboles.
2. Utiliser `exchangeInfo`, mark/index, funding et microstructure pour filtrer les champions.
3. Garder le testnet pour tester le format d'ordre, les signatures et les garde-fous.
4. Ne pas placer d'ordre demo tant qu'une lane n'a pas passe le truth report + microstructure.
