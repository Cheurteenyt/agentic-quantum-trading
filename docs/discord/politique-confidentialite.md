# Politique de Confidentialité — le bot Core Equity

Dernière mise à jour : 05/10/2026 · Contact : le propriétaire du serveur (@cheurteen)

## Ce que le bot collecte

Le bot Core Equity opère exclusivement sur le serveur Discord « Core Equity » et collecte :

1. **Les messages** postés dans les salons du serveur : le contenu, l'auteur (id et nom),
   le salon, l'horodatage, les pièces jointes (type, URL, nom de fichier, taille) et les
   liens contenus dans le texte.
2. **Les métadonnées des membres** : l'id Discord, le nom d'affichage, les rôles, la date
   d'arrivée, la date de création du compte Discord, la dernière activité.
3. **Les appels de trading** postés dans les salons dédiés : le symbole, la direction, le
   prix d'entrée déclaré — scorés automatiquement contre les prix publics collectés.
4. **Les actions de modération** : chaque sanction (warn, mute, kick, ban), son auteur, sa
   cible et sa raison.
5. **Les snapshots des permissions** des salons : les drapeaux privés, les overwrites par
   rôle et par membre, les listes d'accès.

## Ce que le bot ne collecte JAMAIS

- Les **messages privés (MP) entre membres** — techniquement impossible pour un bot et
  interdit par notre charte.
- Les données hors du serveur (aucun autre serveur, aucun autre service).
- Les contenus des MP reçus par le bot lui-même sont scannés pour la détection d'arnaque
  et stockés uniquement à des fins de signalisation.

## Où les données vivent

Toutes les données sont stockées dans une base SQLite **locale, sur la machine du
propriétaire du serveur** — aucune donnée n'est transmise à un tiers, aucun cloud, aucun
service d'analyse externe. Le modèle d'intelligence utilisé pour la modération sémantique
tourne localement sur la même machine.

## Pourquoi

- La modération et la sécurité du serveur (anti-scam, anti-raid, anti-impersonation).
- Le scoring des appels de trading des membres contre les prix publics.
- La traçabilité des actions de modération (l'audit).

## La rétention

- Les messages et les médias : conservés sans limite de temps tant que le serveur existe.
- Les snapshots d'accès : l'historique des modifications (un événement de sécurité).
- La suppression d'un membre du serveur retire son enregistrement du registre des membres.

## Tes droits

Tout membre peut demander : la consultation des données le concernant, leur correction, ou
leur suppression — en contactant le propriétaire du serveur. Les actions de modération
conservent leur trace d'audit (l'intégrité du serveur prime).

## Le consentement

En rejoignant le serveur « Core Equity », tu acceptes cette politique. Le refus des intents
de message à l'entrée (la case Discord) ou la sortie du serveur stoppe toute collecte te
concernant.
