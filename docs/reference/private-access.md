# Core Equity Private Access

Objectif: rendre le site accessible a des clients sans ouvrir directement le PC ni l'API FastAPI au public.

Guide operationnel gratuit: `D:\trading-agent\docs\free-client-access.md`

## Mode recommande

1. Publier le site via un tunnel Zero Trust, pas via une redirection de port routeur.
2. Garder `uvicorn` sur `127.0.0.1:8000` ou `0.0.0.0:8000` uniquement cote machine locale.
3. Activer le verrou applicatif Core Equity avec un token fort.
4. Mettre Cloudflare Access ou Tailscale devant le tunnel pour limiter les clients autorises.

## Variables Core Equity

```env
CORE_ACCESS_TOKEN=change-me-long-random-token
CORE_REQUIRE_LOCAL_AUTH=true
CORE_ALLOWED_HOSTS=localhost,127.0.0.1,ton-domaine-prive.example.com
CORE_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://ton-domaine-prive.example.com
```

## Options de tunnel

- Cloudflare Tunnel + Cloudflare Access: meilleur choix client final. Pas de port entrant ouvert, login par email/IdP, politiques par utilisateur.
- Tailscale Serve: excellent si chaque client peut rejoindre ton tailnet. C'est prive par defaut dans le reseau Tailscale.
- Eviter Tailscale Funnel ou une redirection de port directe pour les clients, sauf si Cloudflare Access ou une protection equivalente est devant.

## Parcours client

### Option A - Clients externes sans installer d'app

1. Tu lances Core Equity sur ton PC.
2. Cloudflare Tunnel expose `http://127.0.0.1:8000` vers un domaine prive, par exemple `https://core.ton-domaine.com`.
3. Cloudflare Access demande au client de se connecter avec son email autorise.
4. Core Equity affiche ensuite son ecran `Core Client Access`.
5. Le client entre le token `CORE_ACCESS_TOKEN` une seule fois. Le site pose un cookie `core_access` valable 12h.

C'est le flux le plus propre pour des clients: pas de port ouvert sur ta box, acces par email, et verrou applicatif en plus.

### Option B - Clients de confiance avec Tailscale

1. Tu ajoutes le client dans ton reseau Tailscale.
2. Tu exposes Core Equity via Tailscale Serve.
3. Le client ouvre l'URL Tailscale depuis son ordinateur.
4. Il entre le token Core Equity si `CORE_REQUIRE_LOCAL_AUTH=true`.

C'est tres prive, mais moins pratique si tu as beaucoup de clients parce qu'ils doivent rejoindre ton tailnet.

## Checklist avant mise en ligne

- `CORE_ACCESS_TOKEN` doit etre long, aleatoire, et different de toutes les cles API.
- `CORE_ADMIN_TOKEN` doit etre long, aleatoire, different de `CORE_ACCESS_TOKEN`, et reserve au proprietaire.
- `CORE_REQUIRE_LOCAL_AUTH=true` doit etre active pour tester le meme comportement en local et en tunnel.
- `CORE_ALLOWED_HOSTS` doit contenir le domaine du tunnel, pas `*`.
- `CORE_ALLOWED_ORIGINS` doit contenir l'origine HTTPS du tunnel.
- Ne partage jamais les cles RPC, Zerion, Cielo, Firecrawl ou autres avec les clients.
- Si un client quitte l'acces, change le token ou retire son email Cloudflare Access.

## Verification rapide

```bash
curl http://127.0.0.1:8000/api/security/status
```

Quand `CORE_ACCESS_TOKEN` est configure, les routes `/api/*` doivent refuser sans cookie/token, et `/api/security/login` doit poser le cookie `core_access`.

Les tokens dans l'URL (`?access_token=...`) sont volontairement refuses. Utilise l'ecran de login ou, pour les scripts proprietaire uniquement, le header `x-core-token`.

Les routes qui controlent le PC, les agents locaux, MT5/NinjaTrader, les probes Scrapling, les stats/reloads Arkham DB, les investigations Intel ou les jobs Firecrawl/Gemini live sont reservees au proprietaire via `CORE_ADMIN_TOKEN` dans le header `x-core-admin-token`. Le token client ne suffit pas.

Les anciennes variables `HERMES_*` restent lues en fallback pour ne pas casser une configuration deja existante, mais les nouveaux deploiements doivent utiliser `CORE_*`.

## Preparation Cloudflare

### 1. Generer le token Core Equity

Depuis PowerShell:

```powershell
D:\trading-agent\scripts\generate_core_access_token.ps1
```

Copie la ligne generee dans `D:\trading-agent\backend\.env`, puis garde ce token prive. Ce token est le deuxieme verrou apres Cloudflare Access.

### 2. Preparer le tunnel

Le modele est dans:

```text
D:\trading-agent\configs\cloudflare-tunnel.example.yml
```

Il doit pointer vers:

```text
http://127.0.0.1:8000
```

Dans Cloudflare Zero Trust:

1. Creer un tunnel.
2. Ajouter un public hostname, par exemple `core.ton-domaine.com`.
3. Service: `http://127.0.0.1:8000`.
4. Ajouter une application Access sur ce hostname.
5. Autoriser uniquement les emails clients.

### 3. Variables a mettre dans `backend\.env`

Exemple pour `https://core.ton-domaine.com`:

```env
CORE_ACCESS_TOKEN=<token-genere>
CORE_REQUIRE_LOCAL_AUTH=true
CORE_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,core.ton-domaine.com
CORE_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://core.ton-domaine.com
```

### 4. Comment les clients accederont au site

Le client recoit uniquement:

```text
https://core.ton-domaine.com
```

Ensuite:

1. Cloudflare verifie son email.
2. Core Equity affiche `Core Client Access`.
3. Le client entre le token Core Equity.
4. Le site fonctionne normalement pendant la session.

Ne donne jamais aux clients:

- les cles API
- les RPC URLs privees
- les fichiers `.env`
- le tunnel credential JSON
