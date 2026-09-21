#!/bin/bash
# Test rapide — vérifier que tout s'intègre correctement

echo "=============================================="
echo "Quick Integration Check"
echo "=============================================="
echo ""

cd /mnt/d/trading-agent/backend

echo "[1/3] Vérifier fichiers modifiés..."
ls -la services/intel_aggregator.py routers/intel.py main.py | awk '{print "  ✓ "$NF}'

echo ""
echo "[2/3] Import Python direct..."
source ../.venv.wsl/bin/activate

python << 'EOF'
import sys
sys.path.insert(0, '/mnt/d/trading-agent')

try:
    from backend.services.intel_aggregator import get_aggregator
    print("✅ IntelAggregator import OK")
    
    from backend.services.websocket_manager import manager
    print("✅ WebSocketManager import OK")
    
    # Instanciate aggregator to check config
    agg = get_aggregator()
    print(f"✅ Aggregator configured:")
    print(f"   • Cooldown: {agg.cooldown_seconds}s")
    print(f"   • Batch interval: {agg.batch_interval}s")
    print(f"   • Max per batch: {agg.max_signals_per_batch}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[OK] Tous les imports réussis!")
EOF

echo ""
echo "[3/3] Lancer backend (optionnel)..."
read -p "Démarrer le backend sur port 8000 ? (y/n) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Starting backend..."
    nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > ../data/logs/backend.log 2>&1 &
    PID=$!
    echo "Backend started with PID: $PID"
    
    sleep 5
    
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend is running!"
        echo ""
        echo "Endpoints disponibles:"
        echo "  • http://localhost:8000/api/intel/status     # Status aggregator"
        echo "  • http://localhost:8000/api/intel/test/signal  # Envoyer test signal"
        echo "  • ws://localhost:8000/ws                      # WebSocket"
        echo ""
        echo "Pour tester:"
        echo "  curl -X POST http://localhost:8000/api/intel/test/signal"
        echo ""
        echo "Pour arrêter:"
        echo "  kill $PID"
    else
        echo "❌ Backend failed to start"
        echo "Voir logs: tail -f ../data/logs/backend.log"
    fi
fi

echo ""
echo "=============================================="
echo "Intégration préparée avec succès!"
echo "=============================================="
echo ""
echo "Architecture connectée:"
echo "  Web-Agent → submit_signal()"
echo "       ↓"
echo "  IntelAggregator (30s cooldown + 5s batch)"
echo "       ↓"
echo "  WebSocket broadcast"
echo "       ↓"
echo "  Frontend React Dashboard"
echo ""
