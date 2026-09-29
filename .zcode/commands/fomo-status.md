---
description: "L'état du pipeline fomo en 60 secondes : watchdog, services, fraîcheur des tables, locks"
---

Fais le point de santé du pipeline fomo du workspace "/run/media/cheurteen/Jeux SSD/trading-agent" (chemin avec espace → TOUJOURS quoter), en lecture seule, et rends un rapport compact en français :

1. Lance `.venv/bin/python scripts/fomo_health.py` (les 4 sondes : ticks figés, collector REST muet, chaîne JWT, locks).
2. `systemctl --user list-timers --no-pager | grep -E "fomo|derek"` : les timers et leurs prochains tirs.
3. En sqlite mode=ro (URI file:...?mode=ro) : la fraîcheur et le volume de fomo_ticks (fomo.db), fomo_mc_samples (fomo.db), fomo_rest_snapshots + fomo_rest_swaps + fomo_rest_token_trades (fomo_rest.db), ws_parking_frames (fomo_swaps.db).
4. `journalctl --user --since "-30 min" --no-pager | grep -cE "database is locked|Traceback"` sur les services fomo.

Format de réponse : une ligne par brique avec son verdict (OK/ALERTE + le chiffre), puis « prochaine action » si quelque chose n'est pas vert. Pas de fix sans demande explicite.
