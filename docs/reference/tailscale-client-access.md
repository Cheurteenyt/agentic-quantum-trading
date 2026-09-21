# Core Equity - Acces client prive via Tailscale

Objectif: partager Core Equity gratuitement avec une URL en chiffres, sans domaine et sans ouvrir de port public.

## Architecture

```text
Client Tailscale
  -> http://100.x.y.z:8000
  -> Tailscale chiffre le trafic
  -> Ton PC
  -> Core Equity
```

`100.x.y.z` est l'adresse Tailscale privee de ton PC. Elle ne fonctionne que pour les appareils autorises dans ton reseau Tailscale.

## Avantages

- Gratuit pour demarrer.
- Pas de domaine a acheter.
- Pas d'URL random.
- Pas de port routeur ouvert.
- IP privee stable en `100.x.y.z`.
- Le trafic est chiffre par Tailscale.
- Core Equity garde son token `CORE_ACCESS_TOKEN` en deuxieme verrou.

## Limites

- Les clients doivent installer Tailscale.
- Tu dois les inviter ou les autoriser dans ton tailnet.
- Si ton PC est eteint, le site est indisponible.
- L'URL sera en `http://100.x.y.z:8000`, pas en HTTPS visible, mais le transport Tailscale est chiffre.

## Installation

### 1. Installer Tailscale sur ton PC

Installer depuis:

```text
https://tailscale.com/download/windows
```

Connecte-toi avec ton compte.

### 2. Recuperer ton IP Tailscale

Dans PowerShell:

```powershell
tailscale ip -4
```

Tu obtiendras une IP du style:

```text
100.64.12.34
```

### 3. Autoriser Core Equity sur cette IP

Dans `D:\trading-agent\backend\.env`, remplace `100.x.y.z` par ton IP Tailscale:

```env
CORE_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,100.x.y.z
CORE_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,http://100.x.y.z:8000
```

Garde aussi:

```env
CORE_ACCESS_TOKEN=<token-prive>
CORE_ADMIN_TOKEN=<token-admin-prive-different>
CORE_REQUIRE_LOCAL_AUTH=true
```

`CORE_ACCESS_TOKEN` est le verrou client. `CORE_ADMIN_TOKEN` est reserve a toi pour les mutations data/admin et doit etre different. Ne mets jamais le token dans l'URL.

### 4. Redemarrer Core Equity

Apres modification du `.env`, redemarre le backend.

### 5. Si le backend tourne dans WSL

Core Equity tourne actuellement dans WSL. Windows voit bien `127.0.0.1:8000`, mais l'IP Tailscale Windows `100.x.y.z` ne redirige pas automatiquement vers WSL.

Il faut creer un portproxy Windows vers l'IP WSL. Dans PowerShell **en administrateur**, remplace `<WSL_IP>` par l'IP retournee par `wsl hostname -I`:

```powershell
netsh interface portproxy add v4tov4 listenaddress=100.x.y.z listenport=8000 connectaddress=<WSL_IP> connectport=8000
New-NetFirewallRule -DisplayName "Core Equity Tailscale 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalAddress 100.x.y.z -LocalPort 8000
```

Pour verifier:

```powershell
netsh interface portproxy show all
```

Pour supprimer plus tard:

```powershell
netsh interface portproxy delete v4tov4 listenaddress=100.x.y.z listenport=8000
```

### 6. Tester depuis ton PC

Depuis ton PC:

```text
http://127.0.0.1:8000
```

Depuis un appareil connecte au meme Tailscale:

```text
http://100.x.y.z:8000
```

## Ce que tu donnes au client

Tu donnes seulement:

```text
1. Installe Tailscale
2. Connecte-toi avec l'email autorise
3. Ouvre http://100.x.y.z:8000
4. Entre le token Core Equity dans l'ecran de login
```

Ne partage pas de lien du type `?access_token=...`. Core Equity refuse volontairement les tokens dans l'URL pour eviter les fuites via historique navigateur, logs, screenshots ou referers.

Ne donne jamais:

- Le fichier `.env`
- Les cles API
- Les URLs RPC privees
- Les identifiants Cloudflare/Tailscale admin

## Retirer un client

Pour retirer un client:

1. Retire son appareil ou son email dans l'admin Tailscale.
2. Si necessaire, regenere `CORE_ACCESS_TOKEN`.
3. Redemarre Core Equity.

## Checklist securite Tailscale

- `CORE_REQUIRE_LOCAL_AUTH=true`
- `CORE_ACCESS_TOKEN` long et different de `CORE_ADMIN_TOKEN`
- `CORE_ALLOWED_HOSTS` contient ton IP Tailscale et aucune wildcard
- `CORE_ALLOWED_ORIGINS` contient `http://100.x.y.z:8000`
- Les endpoints admin utilisent `CORE_ADMIN_TOKEN`, jamais le token client
- Les clients n'ont jamais les cles API/RPC/Zerion/Cielo/Firecrawl
- Si possible plus tard, preferer Tailscale Serve HTTPS ou un hostname prive pour que les cookies puissent etre `Secure`

## Routes reservees au proprietaire

Ces routes sont bloquees pour les clients meme s'ils ont `CORE_ACCESS_TOKEN`. Elles demandent `CORE_ADMIN_TOKEN` via le header `x-core-admin-token`:

- `/api/desktop/*`
- `/api/vision/*`
- `/api/agents/*`
- `/api/chat/*`
- `/api/intel/*`
- `/api/arkham/scrapling/*`
- `/api/arkham/db/*`
- `/api/market/mt5/*`
- `/api/market/ninjatrader*`
- `GET /api/news/gold`
- `GET /api/news/gold/bias`
- `GET /api/news/search`
- `POST /api/arkham/scrape/full`
- `POST /api/arkham/scrape/delta`
- `POST /api/arkham/db/reload`
- `POST /api/opportunities/scan`
- `POST /api/news/gold/refresh`

Raison: ces surfaces peuvent controler le PC, lire l'ecran, lancer des agents locaux, toucher a NinjaTrader/MT5, declencher Scrapling/Firecrawl/Gemini, modifier/recharger la base locale ou consommer des credits/API. Un client doit pouvoir consulter Core Equity, pas piloter ton poste.
