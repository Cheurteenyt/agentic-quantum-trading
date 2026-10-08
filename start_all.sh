#!/bin/bash
# Hermes Trading Control Center — lanceur omarchy (réécrit 2026-09, migration WSL→omarchy)
# Architecture :
#   - Collector Hyperliquid + Aggr.trade intégrés dans FastAPI
#   - APIs externes (CoinGlass, Coinalyze, CounterFlow) intégrées
# La campagne nocturne ne passe plus par ici : systemd user timer
# trading-agent-nightly.timer (03h00, ~/.config/systemd/user/).

cd "/run/media/cheurteen/Jeux SSD/trading-agent" || exit 1
source configs/cache-env.sh
source .venv/bin/activate

echo "============================================"
echo " HERMES TRADING CONTROL CENTER (omarchy)"
echo "============================================"

# S2 : la boucle locale par défaut. `--host 0.0.0.0` exposait toutes les
# routes /api/* au réseau alors que le mode « local-open » se définit par
# l'absence de CORE_ACCESS_TOKEN — c'est-à-dire l'état par défaut. Pour
# exposer volontairement : CORE_HOST=0.0.0.0 CORE_ACCESS_TOKEN=… ./start_all.sh
# (le backend refuse de démarrer sur une interface large sans token).
BACKEND_HOST="${CORE_HOST:-127.0.0.1}"

echo "[1/2] FastAPI Backend port 8000 (bind ${BACKEND_HOST})..."
(cd backend && python3 -m uvicorn main:app --host "$BACKEND_HOST" --port 8000) &
BACKEND_PID=$!

echo "[2/2] Frontend React port 5173 (bind ${CORE_FRONTEND_HOST:-127.0.0.1})..."
(cd frontend && npm run dev -- --host "${CORE_FRONTEND_HOST:-127.0.0.1}") &
FRONTEND_PID=$!

echo ""
echo "============================================"
echo " SERVICES ACTIFS"
echo "============================================"
echo " Backend   : http://localhost:8000"
echo " Frontend  : http://localhost:5173"
echo " API Docs  : http://localhost:8000/docs"
echo "============================================"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Arrete.'; exit" EXIT
wait
