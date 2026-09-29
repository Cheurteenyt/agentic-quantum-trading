---
description: "Audit profond du pipeline fomo (défaut : tout) — $ARGUMENTS = la cible (service, table, script, token)"
---

Audit profond en lecture seule du pipeline fomo sur "/run/media/cheurteen/Jeux SSD/trading-agent" (chemin avec espace → TOUJOURS quoter). Cible : $ARGUMENTS (si vide : tout le pipeline).

Le référentiel de l'audit : docs/23-maitrise-fomo.md (la matrice + le référentiel chart↔trader), les skills .zcode/skills/fomo-pipeline-ops et fomo-rest-api, scripts/README.md (la carte des fichiers).

Procédure :
1. Ce qui TOURNE : systemctl --user (services + timers fomo/derek), les journaux 6 h (database is locked, Traceback, les lignes de passe [rest]/[parking]/[session], most_held).
2. Ce qui GRANDIT : COUNT + MAX(captured_at) par table des bases fomo.db / fomo_swaps.db / fomo_rest.db / fomo_mobula.db / fomo_paper.db (mode=ro) — ce qui est figé = un suspect.
3. Ce qui EST COHÉRENT : les chiffres vs docs/23 (chaque surface a son remplaçant REST nommé), les 1-écrivain-par-base (lslocks si suspicion), la fraîcheur du JWT (exp > now+600 sur les 2 caches).
4. Ce qui MANQUE : les gaps de la matrice docs/23 (les 🟡/❌), les données reçues non persistées (taille de data/fomo/ws_frame_parking.jsonl).

Verdict par brique (OK / À SURVEILLER / PROBLÈME avec la preuve chiffrée), puis la liste ordonnée des actions correctives proposées — SANS les appliquer sans demande explicite. Français, chiffré, max 50 lignes.
