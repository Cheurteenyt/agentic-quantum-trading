#!/bin/bash
# bonsai_idle_stop.sh — le watchdog d'inactivité du serveur Bonsai local.
# Appelé par le timer systemd user (toutes les 5 min, IDLE_MIN=20) :
#   - service inactif → rien à faire
#   - une requête complétée (print_timing) dans la fenêtre → on laisse tourner
#   - un slot en cours de génération (/health include_slots) → on ne coupe PAS
#   - sinon → systemctl --user stop (la VRAM est rendue ; le MCP relance à la demande)
IDLE_MIN="${1:-20}"
SERVICE="bonsai-llama-server"

systemctl --user is-active --quiet "$SERVICE" || exit 0

# une génération en cours ? (on ne coupe jamais mid-generation)
HEALTH=$(curl -s -m 3 "http://127.0.0.1:8080/health?include_slots=1" 2>/dev/null || echo "")
if echo "$HEALTH" | grep -q '"is_processing": *true'; then
    echo "$(date -Is) génération en cours — stop différé"
    exit 0
fi

# une requête complétée dans la fenêtre d'inactivité ?
n=$(journalctl --user -u "$SERVICE" --since "-${IDLE_MIN} min" --no-pager 2>/dev/null | grep -c "print_timing")
if [ "$n" -gt 0 ]; then
    exit 0
fi

systemctl --user stop "$SERVICE"
echo "$(date -Is) bonsai stoppé (aucune requête depuis ${IDLE_MIN} min) — le MCP relancera à la demande"
