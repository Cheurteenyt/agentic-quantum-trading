# LE PORTAIL DÉVELOPPEUR + OAUTH2 (05/10) — Discord dev géré

## L'état configuré (vérifié ce jour)

| Élément | Valeur | Où |
|---|---|---|
| App « Core Equity » | id 1475139333077073951 | portail → Informations générales |
| Description | remplie (modération autonome, capture, compagnon) | API PATCH /applications/@me |
| Permissions d'installation | 1099780140054 (alignées sur le re-invite validé) | API PATCH |
| Tags | moderation, trading, communaute | API PATCH |
| Client secret OAuth2 | généré + validé (token app obtenu, scope identify) | `.env` → `DISCORD_CLIENT_SECRET` (chmod 600) |
| URI de redirection | `http://localhost:8080/oauth2/callback` (persisté, vérifié au reload) | portail → OAuth2 → Redirections |
| Intents privilégiés | actifs (preuve : le bot tourne en prod avec message_content + members) | portail → Bot |

## La répartition sécurité (la règle qui tient)

- Le user tape **son** login + 2FA (ou scanne le QR) — l'agent ne voit jamais les credentials.
- L'agent pilote les clics via CDP (chromium lancé avec `--remote-debugging-port=9223`).
- L'agent ne régénère JAMAIS le token du bot (le `hermes-discord.service` tomberait).
- Le reset de la clé secrète exige le code 2FA du user — c'est le portail qui impose la double main.

## Rouvrir le portail (la session Discord reste dans le profil)

```bash
systemctl --user start discord-dev-browser   # le profil data/discord_dev_browser garde la session
# pilotage CDP : http://localhost:9223 (playwright connect_over_cdp)
systemctl --user stop discord-dev-browser    # fermer proprement
```

Unit : `discord-dev-browser.service` (chromium ms-playwright, profil séparé du fomo).

## Le test de bout en bout (le secret validé)

```bash
curl -s -X POST https://discord.com/api/v10/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&scope=identify" \
  -u "$DISCORD_CLIENT_ID:$DISCORD_CLIENT_SECRET"
# → access_token (7 j) = la clé est bonne
```

## Ce que ça débloque (le futur dashboard)

Les membres se connectent avec Discord (OAuth2 authorization_code, redirect
`http://localhost:8080/oauth2/callback`) → le dashboard affiche leurs calls,
leur rang du leaderboard, leurs stats de modération. Les clés sont prêtes
(`DISCORD_CLIENT_ID` + `DISCORD_CLIENT_SECRET` dans `.env`, exposées dans
`discord_bot/config.py`), rien d'autre ne bloque.

## La gestion continue (05/10, l'état complet)

```
.venv/bin/python scripts/discord_dev.py status    # l'audit complet en 1 commande
.venv/bin/python scripts/discord_dev.py sync-global   # globales = la guilde
.venv/bin/python scripts/discord_dev.py webhooks / invite
```

L'état au 05/10 : commandes **36 globales = 36 guilde** (69 fantômes purgés),
webhooks 2 (les siens, aucun orphelin), intents privilégiés 3/3 ON (prouvé par
libellé), code grant OFF, **bot passé en PRIVÉ** (sauvé au portail — se
re-confirmer au prochain login), install_params 1099780140054.

⚠ LA SESSION PORTAIL VIT AUSSI LONGTEMPS QUE LE PROCESS NAVIGATEUR — chaque
redémarrage du chromium force un re-login Discord. **Laisser
`discord-dev-browser` tourner** au lieu de le stopper : la fenêtre reste sur
l'écran de login quand la session est morte, le QR règle ça en 10 secondes.

⚠ L'API Discord derrière Cloudflare : curl nu = OK ; urllib/httpx par défaut =
souvent OK ; httpx avec un UA Chrome spoofé = 40333 systématique (le TLS ne
 colle pas avec l'UA). `scripts/discord_dev.py` subprocess du curl nu, jamais
de spoof.
