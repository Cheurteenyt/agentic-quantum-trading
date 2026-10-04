# Le bot Discord Hermes — le setup en 4 minutes

## 1. Le portail développeur (une fois)
1. https://discord.com/developers/applications → **New Application** → nomme-le « Hermes »
2. Onglet **Bot** :
   - **Reset Token** → copie le token (il ne se ré-affiche jamais) → colle-le dans `.env` → `DISCORD_BOT_TOKEN=`
   - **Privileged Gateway Intents** : active **Message Content Intent** ✅ et **Server Members Intent** ✅
     (sans eux le bot ne lit aucun texte et ne voit pas les membres — le bot refusera de démarrer sans)
3. Onglet **OAuth2** → copie le **Client ID**

## 2. L'invitation (le bot « voit tous les salons »)
Colle dans ton navigateur en remplaçant CLIENT_ID :
```
https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&permissions=68608&scope=bot%20applications.commands
```
`permissions=68608` = Voir les salons (1024) + Envoyer des messages (2048) + Lire l'historique (65536).
Sur la page d'invitation : choisis TON serveur → Autoriser. Le bot apparaît dans la liste des membres
et voit tous les salons autorisés par ses permissions côté serveur (aucun salon à ajouter à la main).

## 3. Le .env (à la racine du repo — GITIGNORED, le token ne sort jamais)
```
DISCORD_BOT_TOKEN=le_token_étape_1
DISCORD_GUILD_ID=clic_droit_sur_ton_serveur_→_Copier_l_id_(mode_développeur)
DISCORD_HOME_CHANNEL=l_id_du_salon_où_le_bot_postera_les_rapports
```

## 4. Le lancement
```
.venv/bin/python -m discord_bot.bot
```
Au démarrage il imprime : la connexion, le nom du serveur, et LA LISTE des salons visibles
(la preuve du « voit tout les salons »). Les slash commands sont sync **sur ta guilde**
(instantané — pas l'heure du sync global). Teste avec `/ping` puis `/etat`.

## 5. La structure (ajouter une commande = un fichier dans cogs/)
```
discord_bot/
├── bot.py          # le client, les intents, le sync de guilde, le chargement des cogs
├── config.py       # lit .env (le token JAMAIS dans git), valide, expose les chemins DB
├── README.md       # ce guide
└── cogs/
    ├── status.py   # /ping, /etat, /membres (lecture seule DB)
    ├── capture.py   # LA CAPTURE : chaque message (texte/médias/liens) → discord.db + backfill
    └── moderation.py # LA MODÉRATION : kick/ban/timeout/warn/clear/lock/roles + auto-mod (spam, mentions, invites) + log #logs
```
Les prochains cogs prévus (l'agent discord-bot du repo) : les rapports quotidiens (stats machine,
alertes de graduation fomo, trades forward, verdicts) postés dans DISCORD_HOME_CHANNEL.

## 6. Le service systemd (le bot démarre au boot, se relance si crash)
L'unité : `~/.config/systemd/user/hermes-discord.service` (ExecStart quoté — le chemin du
repo contient un espace ; `PYTHONUNBUFFERED=1` pour que les logs arrivent au journal).
```
systemctl --user status hermes-discord    # l'état
journalctl --user -u hermes-discord -f    # les logs en direct
```
Les commandes live : `/ping` · `/etat` (l'état du projet) · `/membres` (les ids des membres —
la détection des identifiants, intents members actifs).
