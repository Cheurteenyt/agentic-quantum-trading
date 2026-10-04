# LE DASHBOARD WEB CORE EQUITY (05/10) — OAuth2 live

## Ce que c'est

Le port 8606 (systemd `core-equity-dashboard.service`) : les membres se
connectent **avec Discord** et voient leur profil, leurs rôles, leurs calls
scorés, le classement et le serveur en direct. Zéro compte à créer — l'OAuth2
est l'authentification.

- `/` l'accueil (le bouton de connexion) · `/moi` le profil (rôles colorés,
  messages capturés, calls + WR + Σ ret) · `/classement` (min. 3 calls scorés,
  même SQL que le bot) · `/serveur` (membres, capture, top salons) ·
  `/api/me` (JSON) · `/logout`.

## La mécanique

- Le flow : `/oauth2/login` → Discord (scopes `identify guilds.members.read`,
  l'état anti-CSRF usage unique 10 min) → `/oauth2/callback` → échange du code →
  cookie `ce_session` signé HMAC-SHA256 (clé = client secret, TTL 7 j, HttpOnly,
  SameSite=Lax).
- Les tokens : `data/dashboard_sessions.json` (chmod 600, hors git) — le refresh
  automatique à l'expiration, le profil re-fetché à chaque /moi (les rôles sont
  toujours à jour).
- Les données : la warehouse `discord.db` en READ-ONLY (d_messages, d_members,
  d_roles, d_calls) — le dashboard ne peut rien écraser. `d_calls` manquant
  (aucun call encore parsé) → pages vides gracieuses, jamais de 500.

## Les pièges résolus (à ne pas retomber dessus)

- Le port : 8606 (8080 = Bonsai au réveil, 8000 = backend). Le redirect URI du
  portail DOIT rester synchronisé : http://localhost:8606/oauth2/callback.
- Le portail Discord n'accepte l'édition du redirect qu'avec de VRAIS événements
  clavier (keyboard.type) — le fill programmatique n'est pas vu par le React.
- systemd : `WorkingDirectory=` n'accepte NI l'espace ni les guillemets → le
  symlink `/home/cheurteen/core-equity` (sans espace) est LE chemin des unités.

## L'exploitation

```bash
systemctl --user status core-equity-dashboard   # actif au boot (enable --now)
journalctl --user -u core-equity-dashboard -f   # les logs
curl -s localhost:8606/serveur -o /dev/null -w '%{http_code}\n'   # le ping
```
