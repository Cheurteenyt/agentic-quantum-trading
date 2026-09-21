# Core Equity - Partage prive gratuit

Objectif: permettre a des clients d'acceder au site qui tourne sur ton PC, sans payer d'hebergeur et sans ouvrir de port sur ta box.

## Architecture recommandee

```text
Client
  -> https://core.ton-domaine.com
  -> Cloudflare Access verification email
  -> Cloudflare Tunnel
  -> Ton PC
  -> Core Equity http://127.0.0.1:8000
```

Tu n'heberges pas le site chez Cloudflare. Le site reste sur ton PC. Cloudflare sert uniquement de tunnel securise et de porte d'entree privee.

Alternative gratuite sans domaine et sans URL random: `D:\trading-agent\docs\tailscale-client-access.md`

## Ce qui est gratuit

- Cloudflare Tunnel: permet d'exposer ton site local sans ouvrir de port.
- Cloudflare Access Free: suffisant pour une petite equipe / premiers clients.
- Core Equity reste lance sur ton PC.

Points a prevoir:

- Il faut un domaine connecte a Cloudflare pour une URL propre comme `core.ton-domaine.com`.
- Sans domaine, on peut tester avec un tunnel temporaire, mais ce n'est pas ideal pour des clients.
- Ton PC doit rester allume et connecte a internet.
- Si ton PC s'eteint, le site devient indisponible.

## Setup resume

### 1. Activer la securite Core Equity

Dans `D:\trading-agent\backend\.env`, ajouter:

```env
CORE_ACCESS_TOKEN=<token-long-et-prive>
CORE_REQUIRE_LOCAL_AUTH=true
CORE_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,core.ton-domaine.com
CORE_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://core.ton-domaine.com
```

Pour generer un token:

```powershell
D:\trading-agent\scripts\generate_core_access_token.ps1
```

### 2. Lancer Core Equity localement

Le backend doit repondre ici:

```text
http://127.0.0.1:8000
```

Verification:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
```

### 3. Creer le tunnel Cloudflare

Dans Cloudflare Zero Trust:

1. Aller dans `Networks > Tunnels`.
2. Creer un tunnel.
3. Installer `cloudflared` sur ton PC.
4. Ajouter un hostname public, exemple `core.ton-domaine.com`.
5. Service local: `http://127.0.0.1:8000`.

Le modele local est ici:

```text
D:\trading-agent\configs\cloudflare-tunnel.example.yml
```

### 4. Proteger avec Cloudflare Access

Dans Cloudflare Zero Trust:

1. Aller dans `Access > Applications`.
2. Ajouter une application self-hosted.
3. Domaine: `core.ton-domaine.com`.
4. Politique: autoriser uniquement les emails clients.
5. Refuser tout le reste.

## Ce que le client recoit

Tu lui envoies seulement:

```text
URL: https://core.ton-domaine.com
Token Core Equity: <token-client>
```

Le client fait:

1. Il ouvre l'URL.
2. Cloudflare demande son email / code.
3. Core Equity affiche `Core Client Access`.
4. Il entre le token.
5. Il accede au dashboard, Arkham local, Alpha Lab, etc.

Ne jamais envoyer un lien qui contient le token dans l'URL. Les URLs peuvent fuiter dans l'historique navigateur, les logs ou les captures d'ecran.

## Rotation d'acces

Pour retirer un client:

- Enleve son email dans Cloudflare Access.
- Si le token a ete partage trop largement, regenere `CORE_ACCESS_TOKEN`.
- Redemarre Core Equity apres changement du `.env`.

## Endpoints exposes

Quand `CORE_ACCESS_TOKEN` est actif:

- `/health` reste public pour verifier que le service repond.
- `/api/security/status` et `/api/security/login` restent publics pour afficher l'ecran d'acces.
- `/api/*` est bloque sans cookie/token Core Equity.
- `/ws` est bloque sans cookie/token Core Equity.
- `/docs`, `/redoc` et `/openapi.json` sont bloques sans cookie/token Core Equity.
- `/assets`, `/brand-icons`, `index.html` et le shell React restent publics pour permettre a l'ecran de login de charger.

## Limites importantes

- Gratuit ne veut pas dire haute disponibilite: ton PC devient le serveur.
- Si plusieurs clients utilisent beaucoup Alpha Lab/RPC en meme temps, les performances dependent de ton PC et de tes providers RPC.
- Ne donne jamais les fichiers `.env`, les cles API, les RPC prives ou les credentials Cloudflare.
- Cloudflare protege l'entree, mais Core Equity garde son propre verrou applicatif en plus.
