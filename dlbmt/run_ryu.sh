#!/bin/bash
# ==============================================================
# DLBMT — Launch Ryu Controller Instances
# ==============================================================
# Usage:
#   NUM_CONTROLLERS=4 ./run_ryu.sh
# Defaults to 3 controllers (Atlanta) if not specified.
# ==============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Config
NUM_CTRLS=${NUM_CONTROLLERS:-3}

# Kill existing ryu instances
pkill -f ryu-manager 2>/dev/null || true
sleep 1

echo "=== Starting $NUM_CTRLS DLBMT Ryu Controllers ==="
echo ""

for i in $(seq 1 $NUM_CTRLS); do
    cid="c$i"
    # Port calculation: 6633 + (i-1)
    port=$((6633 + i - 1))
    
    echo "[$i/$NUM_CTRLS] Starting $cid on port $port..."
    
    DLBMT_CONTROLLER_ID=$cid ryu-manager ryu_dlbmt_app.py \
        --ofp-tcp-listen-port $port \
        > $cid.log 2>&1 &
        
    sleep 2
done

# Health check
RUNNING=$(pgrep -c -f ryu-manager || true)
echo ""
echo "=== $RUNNING Ryu controller(s) running ==="
echo "    Check logs: c1.log, c2.log..."
echo ""
echo "Next steps:"
echo "  Terminal 2: sudo python3 topo_multi.py --topo <name>"
echo "  Terminal 3: export DLBMT_TOPO=<name>; python3 app.py"
echo "  Terminal 4: cd frontend && npm run dev"
