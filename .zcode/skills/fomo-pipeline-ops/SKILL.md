---
name: fomo-pipeline-ops
description: L'exploitation et le debug du pipeline de collecte fomo (services systemd, bases SQLite, timers, locks). Utiliser pour « debug fomo », « database is locked », un service qui n'écrit plus, un audit du pipeline, l'ajout d'un collecteur ou d'un timer, ou toute écriture dans fomo.db / fomo_swaps.db / fomo_rest.db — même si l'utilisateur dit juste « vérifie la collecte ».
---

# Le pipeline fomo — exploitation et debug

## La carte (4 services + les timers)

- `fomo-browser.service` — Chrome dédié, CDP :9222 (worker) / :9223 (walker, session loggée)
- `fomo-dom-worker.service` — 1 page permanente :9222, les routes DOM (SCHEDULE déclaratif, 10 surfaces `do_*`)
- `fomo-ws-daemon.service` — socket natif `wss://prod-api.fomo.family/ws` (challenge JWT, plafond ~80 topics, pacing 0,05 s) ; **re-mint le JWT via CDP 24/7**
- `fomo-rest-collector.timer` (30 min) + swaps-fresh (hourly) + mobula-topup + paper-forward + session-monitor

## Les bases — UN SEUL ÉCRIVAIN par base (la loi)

| Base | Écrivain | Contenu |
|---|---|---|
| `fomo.db` | daemon seul | ticks 2 s, fomo_tokens, ws_signals, dom_* |
| `fomo_swaps.db` | worker DOM | fomo_token_holders/theses/header/swap_history |
| `fomo_rest.db` | collector REST | fomo_rest_snapshots, fomo_rest_swaps |

Lire TOUJOURS en read-only : `sqlite3.connect("file:...?mode=ro", uri=True)`.
Deux écrivains sur une même base = jamais (WAL ou pas).

## Les 3 leçons de mort (la panne du 29/09)

1. **La txn d'écriture = un commit PAR PASSE.** Une connexion ouverte au boot
   + des INSERT sans `.commit()` = le verrou WAL tenu à vie → TOUT le daemon
   gèle (0 tick pendant 1h30, 378 flush différés). Diagnostic : `lslocks`
   (le process tient le write lock), mtime du `-wal` figé, COUNT/MAX qui
   n'avancent plus. Le fix : `con.commit()` en fin de chaque store.
2. **Le DDL vit dans `ensure_tables`/`ensure_dbs` ; l'INSERT = liste de
   colonnes explicite.** Un CREATE inline dans une route avalé par `except`
   ne crée JAMAIS la table (swap_history) ; un ALTER désynchronisé de
   l'INSERT déraille en silence (header 15 cols vs 14 valeurs) ; un parseur
   non importé = NameError avalé = pertes sans bruit.
3. **État persistant + timeout systemd = un état qui ne s'écrit jamais.**
   Un budget interne ou un commit par token, sinon le kill arrive avant.

## Le diagnostic standard (dans l'ordre)

1. `systemctl --user status fomo-dom-worker fomo-ws-daemon fomo-rest-collector --no-pager`
2. `journalctl --user -u <service> --since "-6 hours" | grep -c "database is locked"` (+ Traceback, + les lignes de passe)
3. sqlite mode=ro : `COUNT(*)` + `MAX(captured_at)` par table → ce qui est figé
4. `lslocks | grep -E "fomo|python"` → qui tient quoi
5. La chronologie : mtime du `-wal` vs les SCHEDULE/routes

## Les pièges du site (gravés)

- Les listes = **virtualisées** → clic `force=True`, scroll conteneur + dédupe
- Les labels = **singuliers avec compteur** (« Thesis (3,846) ») — jamais le pluriel
- La nav = 100 % clics SPA ; une URL directe = « Go home »
- patchright `evaluate` = **monde isolé** : un hook `window.WebSocket` y est
  invisible — capturer via `page.on("websocket")` (framereceived/framesent)
- Réutiliser une page déjà ouverte du daemon, TOUJOURS fermer la sienne
  (`finally`) — la leçon de la page qui flash
- Avant de croire un chiffre forward : auditer l'évaluateur d'abord
