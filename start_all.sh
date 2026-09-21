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

echo "[1/2] FastAPI Backend port 8000..."
(cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload) &
BACKEND_PID=$!

echo "[2/2] Frontend React port 5173..."
(cd frontend && npm run dev -- --host 0.0.0.0) &
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
