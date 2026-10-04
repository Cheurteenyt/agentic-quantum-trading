# LA RÉFÉRENCE DISCORD DEVELOPER DOCS (05/10) — la carte doc ↔ modules

La source : https://docs.discord.com/developers/intro — chaque page est fetchable en
markdown (le suffixe `.md` sur toute URL, ex : /developers/intro.md) — parfait pour le
dev assisté : la doc exacte au moment de coder, pas de la mémoire approximative.

## La carte : nos modules en attente ↔ les sections de la doc

| Module (l'analyse d'écart 05/10) | Les sections de la doc à lire |
|---|---|
| Les tickets asynchrones (/ticket) | **Components & Modals** (les modals = les formulaires d'ouverture) · **Interactions & Commands** |
| Le RBAC quarantaine 48 h | **Server & Channel Management** · **OAuth2 & Permissions** |
| Les rôles par activité / le portier | **Server & Channel Management** (les overwrites, les rôles automatiques) |
| Le feed du labo (les alertes) | **Webhooks** (l'alternative légère au gateway pour les pushes one-way) |
| La monétisation VIP native | **Monetization → Premium Apps & Activities** · **Social Commerce** |
| La croissance (les 100 serveurs → la vérification) | **Growth & Distribution → App Discovery** · **Managing Developer Team** (l'équipe, la 2FA des membres) |
| Les salons communautaires | **Community Servers** |

## La règle de dev

Toute fonctionnalité Discord nouvelle commence par : fetch de la section doc en markdown
→ le design → le code. La doc est la source de vérité sur les rate limits et les
permissions exactes — pas Bonsai, pas ma mémoire.

## Le détail des sections pertinentes (le plan de la doc)

- App Fundamentals : Overview of Apps · Discord Bots · OAuth2 & Permissions ·
  Interactions & Commands · Components & Modals · Server & Channel Management · Webhooks
- Game & Platform : Account Linking · Social Layer · Rich Presence · Activities ·
  Community Servers
- Growth & Distribution : App Discovery · Grow Your Game
- Monetization : Premium Apps & Activities · Social Commerce
- Tools : Community Resources · Managing Developer Team
- Policies : Developer Policy · Developer Terms of Service (nos CGU doivent coller)
