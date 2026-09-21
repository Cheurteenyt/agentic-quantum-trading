# Aster MCP - Connexion wallet Phantom sans risque

Date: 2026-05-31  
Statut: procedure de preparation. Aucun trading reel.

## Conclusion courte

Phantom ne se connecte pas directement au MCP comme une extension navigateur.

Le flux correct est:

1. Phantom signe dans l'interface Aster officielle via WalletConnect ou connexion wallet.
2. Aster cree ensuite soit une API key HMAC, soit un Agent/API Wallet V3.
3. Le MCP Aster stocke ces credentials localement dans sa configuration chiffree.
4. Core Equity ne doit lire que les outils read-only via un wrapper.

Regle absolue:

- ne jamais mettre la seed Phantom dans le projet;
- ne jamais exporter la private key principale Phantom dans le MCP;
- ne jamais utiliser un wallet principal ou charge en fonds pour les tests;
- ne jamais activer ordres/transferts dans Core Equity a ce stade.

## Ce que dit le repo Aster MCP

Le repo `asterdex/aster-mcp` supporte deux modes d'auth:

- `HMAC`: API Key + API Secret;
- `V3 key signing`: `user` main wallet + `signer` API wallet + `private_key` du signer.

Les credentials sont stockes localement dans `~/.config/aster-mcp/` avec chiffrement Fernet.

Important:

- le MCP expose aussi `create_order`, `cancel_order`, `set_leverage`, `set_margin_mode`, `transfer_funds`;
- donc on ne doit pas connecter l'agent Core Equity au MCP brut;
- il faut un wrapper read-only.

## Setup Phantom recommande

### 1. Creer un wallet Phantom dedie

Utiliser un wallet neuf, separe du wallet principal.

Nom conseille:

`CoreEquity-Aster-Test`

Regles:

- zero seed phrase dans les fichiers;
- zero screenshot de seed;
- zero partage dans le chat;
- peu ou pas de fonds;
- si besoin de signer sur BNB Chain, garder seulement le minimum requis par Aster.

### 2. Connecter Phantom a Aster

Dans l'interface Aster:

1. ouvrir l'app Aster officielle;
2. choisir la chaine voulue;
3. connecter le wallet;
4. si Phantom n'apparait pas en direct, utiliser WalletConnect;
5. signer uniquement les messages clairement lies a la connexion ou a la creation API/Agent.

Si la connexion Phantom echoue sur BNB Chain:

- tester via WalletConnect;
- sinon utiliser un wallet EVM dedie plus standard pour BNB, par exemple Rabby ou MetaMask;
- ne pas forcer avec une private key exportee.

## Deux chemins possibles

### Chemin A - HMAC API key read-only

C'est le chemin le plus simple pour nous si Aster permet des permissions read-only.

Procedure:

1. Phantom connecte a Aster UI.
2. Aller dans API Management.
3. Creer une API key dediee.
4. Nom: `core-equity-readonly`.
5. Permissions: read-only uniquement si disponible.
6. Aucun withdraw.
7. Aucun trade si l'UI permet de le desactiver.
8. Ajouter restriction IP si Aster le permet.
9. Copier API key + secret une seule fois.
10. Configurer dans Aster MCP via:

```powershell
Set-Location D:\trading-agent
# apres installation isolee du MCP
external\aster-mcp\.venv\Scripts\aster-mcp config --account-id core_readonly
```

Dans ce mode, le MCP utilisera `HMAC`.

Risques:

- si Aster ne propose pas de vraie permission read-only, ne pas utiliser cette key dans Core Equity;
- ne jamais donner une key avec withdraw;
- ne jamais committer la config MCP.

### Chemin B - V3 Agent/API Wallet

C'est le chemin plus propre pour une architecture future, mais plus sensible.

Principe:

- Phantom est le `user` main wallet;
- Aster genere ou autorise un `signer` / Agent API Wallet;
- le signer a sa propre private key;
- cette private key n'est pas la private key Phantom principale.

Procedure conceptuelle:

1. Phantom connecte a Aster UI.
2. Ouvrir la page Agent/API Wallet si disponible.
3. Creer ou autoriser un nouvel Agent.
4. Restreindre les permissions au strict minimum.
5. Sauvegarder l'adresse signer et la private key signer hors repo.
6. Configurer Aster MCP:

```powershell
Set-Location D:\trading-agent
# apres installation isolee du MCP
external\aster-mcp\.venv\Scripts\aster-mcp config --account-id core_v3 --auth-type v3
```

Valeurs attendues:

- `user`: adresse publique Phantom/main wallet;
- `signer`: adresse de l'Agent/API Wallet;
- `private_key`: private key du signer, pas la key Phantom principale.

Risques:

- meme si c'est un signer, il peut avoir des permissions de trading;
- ne pas le brancher a l'agent avant un vrai wrapper read-only;
- si une permission trading est obligatoire, ne pas l'utiliser dans Core Equity pour l'instant.

## Phase 0 sans credentials

Avant toute key, on peut deja utiliser Aster MCP ou notre code actuel pour:

- `get_ticker`;
- `get_order_book`;
- `get_klines`;
- `get_funding_rate`;
- `get_funding_info`;
- `get_exchange_info`;
- `ping`.

Ces outils ne necessitent pas de wallet ou d'account id.

C'est la phase conseillee avant de connecter Phantom.

## Phase 1 avec compte read-only

Objectif:

- verifier balances et positions en lecture seule;
- recuperer commission rate;
- recuperer leverage brackets reels;
- comparer avec notre proxy perps.

Outils autorises:

- `get_balance`;
- `get_positions`;
- `get_account_info`;
- `get_account_v4`;
- `get_commission_rate`;
- `get_leverage_bracket`;
- spot equivalents read-only.

## Donnees Aster Code / RPC a connaitre

La documentation officielle confirme un modele Agent/Builder:

- un `Agent/API Wallet` est un signer approuve par le wallet principal;
- permissions explicites: `canSpotTrade`, `canPerpTrade`, `canWithdraw`;
- `canWithdraw` doit rester `false` dans Core Equity;
- l'Agent peut avoir une expiration et une IP whitelist;
- un Builder peut avoir un `maxFeeRate` approuve par l'utilisateur.

Si un jour on sort du read-only, la policy minimale devra imposer:

- signer dedie par environnement;
- expiration courte;
- IP whitelist obligatoire si disponible;
- aucune permission withdrawal;
- aucune key principale Phantom dans le repo;
- aucun ordre sans confirm manuel separe.

RPC utile mais limite:

- `https://tapi.asterdex.com/info` peut lire balance/open orders/fills par adresse;
- la privacy peut masquer les details;
- les fills sont limites a 7 jours;
- usage acceptable: verifier notre propre adresse;
- usage refuse: scanner des wallets tiers.

## Donnees publiques deposit/withdraw

La documentation Aster expose des endpoints publics pour connaitre les assets et
frais par chaine.

Smoke du 2026-05-31:

- BNB Chain / EVM / spot: `53` assets deposit;
- BNB Chain / EVM / spot: `53` assets withdraw;
- estimate withdraw fee ASTER: `gasCost=0.1389`, `gasUsdValue=0.1`.

Usage autorise:

- preparer une checklist wallet;
- verifier qu'un asset/chain est supporte;
- estimer un cout de retrait avant une decision manuelle.

Usage interdit:

- transfert automatique;
- withdrawal signe;
- integration dans les runners de backtest;
- stockage de secrets.

Outils interdits:

- `create_order`;
- `create_spot_order`;
- `cancel_order`;
- `cancel_all_orders`;
- `set_leverage`;
- `set_margin_mode`;
- `transfer_funds`;
- `transfer_spot_futures`.

## Phase 2 Core Equity wrapper

Avant de connecter le MCP au moteur:

creer un module:

`backend/services/onchain/aster/aster_mcp_market_data_adapter.py`

Responsabilites:

- allowlist stricte des outils read-only;
- normaliser funding, fees, leverage brackets;
- retourner `would_execute_trade=false`;
- retourner `would_transfer=false`;
- bloquer tout outil non allowlist.

## Checklist avant qu'on configure quoi que ce soit

- [ ] Wallet Phantom dedie cree.
- [ ] Seed phrase sauvegardee hors ligne, jamais dans le repo.
- [ ] `external/aster-mcp` installe dans environnement isole.
- [ ] Pas de key dans `.env` backend.
- [ ] Pas de key committee.
- [ ] API key read-only ou Agent signer cree avec permissions minimales.
- [ ] Aster MCP `list` fonctionne.
- [ ] Aster MCP `test account_id` fonctionne.
- [ ] Wrapper read-only Core Equity cree avant integration au moteur.
- [ ] RAG mis a jour.

## Commandes utiles plus tard

Installation isolee, uniquement quand on decide de l'installer:

```powershell
Set-Location D:\trading-agent
New-Item -ItemType Directory -Force external
git clone https://github.com/asterdex/aster-mcp external\aster-mcp
py -3.11 -m venv external\aster-mcp\.venv
external\aster-mcp\.venv\Scripts\python -m pip install -e external\aster-mcp
```

Configuration HMAC:

```powershell
external\aster-mcp\.venv\Scripts\aster-mcp config --account-id core_readonly
```

Configuration V3:

```powershell
external\aster-mcp\.venv\Scripts\aster-mcp config --account-id core_v3 --auth-type v3
```

Verifier les comptes:

```powershell
external\aster-mcp\.venv\Scripts\aster-mcp list
external\aster-mcp\.venv\Scripts\aster-mcp test core_readonly
```

Demarrer en stdio:

```powershell
external\aster-mcp\.venv\Scripts\python -m aster_mcp.simple_server
```

## Decision actuelle

On peut avancer sur la preparation Phantom, mais la premiere vraie etape doit
rester sans execution:

1. creer un wallet Phantom dedie;
2. connecter ce wallet a Aster UI;
3. verifier si Aster permet une API key read-only;
4. ne pas creer de key trading dans Core Equity;
5. installer le MCP seulement dans `external/aster-mcp`;
6. tester public market data avant toute authentification;
7. construire le wrapper read-only avant de lire balances/positions.
