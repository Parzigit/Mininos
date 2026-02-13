"""
DLBMT Dashboard — Flask + SocketIO Backend
============================================
Receives real-time metrics from Ryu controllers, runs DLBMT load
balancing, and serves REST + WebSocket API for the React frontend.
"""

import os
import time
import logging
import threading

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO

from real_dlbmt_engine import RealDLBMTEngine

# =====================================================================
#  Flask setup
# =====================================================================

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("dlbmt.app")

# =====================================================================
#  Engine & state
# =====================================================================

# Controls
TOPO_NAME = os.environ.get("DLBMT_TOPO", "atlanta")
engine = RealDLBMTEngine(topology_name=TOPO_NAME)
sim_lock = threading.Lock()

# Controls
auto_migration_enabled = True
polling_interval = 1.0  # seconds

# =====================================================================
#  Ryu update endpoint — receives metrics from each Ryu controller
# =====================================================================

@app.route("/api/ryu/update", methods=["POST"])
def ryu_update():
    """
    Called by each Ryu controller instance every second.
    Payload: {controller_id, cpu, memory, switches: {dpid: pkt_count}}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "no data"}), 400

    with sim_lock:
        engine.update_controller_metrics(data)

    return jsonify({"ok": True})


# =====================================================================
#  REST API — Topology
# =====================================================================

@app.route("/api/topology")
def get_topology():
    """Return topology data for the frontend TopologyView component."""
    with sim_lock:
        snapshot = engine.take_snapshot()

    nodes = []
    links = []

    # Controllers
    for cid, ctrl in engine.controllers.items():
        cdata = snapshot["controllers"].get(cid, {})
        nodes.append({
            "id": cid,
            "type": "controller",
            "x": ctrl.x,
            "y": ctrl.y,
            "load": cdata.get("load", 0),
            "level": cdata.get("level", 1),
            "level_label": cdata.get("level_label", "Idle"),
            "level_color": cdata.get("level_color", "#00ff88"),
            "switch_count": cdata.get("switch_count", 0),
            "capacity_cpu": ctrl.capacity_cpu,
            "capacity_mem": ctrl.capacity_mem,
            "capacity_bw": ctrl.capacity_bw,
        })

    # Switches
    mapping = engine.build_mapping()
    for cid, sw_ids in mapping.items():
        for sid in sw_ids:
            sw = engine.switches.get(sid)
            if not sw:
                continue
            nodes.append({
                "id": sid,
                "type": "switch",
                "controller_id": cid,
                "x": sw.x,
                "y": sw.y,
                "packet_in_rate": round(sw.packet_in_rate, 1),
                "load_cpu": round(sw.load_cpu, 2),
                "load_mem": round(sw.load_mem, 2),
                "load_bw": round(sw.load_bw, 4),
                "resource_usage": round(
                    engine._switch_resource_usage(sw, engine.controllers[cid]) * 100, 2
                ),
            })
            links.append({
                "source": cid,
                "target": sid,
                "type": "domain",
            })

    # Infrastructure links (switch-to-switch)
    for src, tgt in engine.get_infra_links():
        links.append({
            "source": src,
            "target": tgt,
        })

    return jsonify({
        "topology_name": getattr(engine, "topology_name", "Unknown"),
        "nodes": nodes,
        "links": links,
    })


# =====================================================================
#  REST API — Controllers
# =====================================================================

@app.route("/api/controllers")
def get_controllers():
    """Return controller data for the ControllerPanel component."""
    with sim_lock:
        result = []
        mapping = engine.build_mapping()

        for cid, ctrl in engine.controllers.items():
            result.append({
                "id": cid,
                "load_percentage": round(ctrl.load_percentage, 2),
                "level": ctrl.level.value,
                "level_label": ctrl.level.label,
                "level_color": ctrl.level.color,
                "switch_count": len(mapping.get(cid, [])),
                "cpu_utilization": round(ctrl.cpu_utilization, 2),
                "mem_utilization": round(ctrl.mem_utilization, 2),
                "bw_utilization": round(ctrl.bw_utilization, 2),
                "capacity_cpu": ctrl.capacity_cpu,
                "capacity_mem": ctrl.capacity_mem,
                "capacity_bw": ctrl.capacity_bw,
                "active": ctrl.active,
            })

    return jsonify(result)


# =====================================================================
#  REST API — Statistics
# =====================================================================

@app.route("/api/stats/summary")
def get_stats_summary():
    """Return aggregate stats for the top stat cards."""
    with sim_lock:
        mapping = engine.build_mapping()
        loads = [c.load_percentage for c in engine.controllers.values() if c.active]
        avg_load = round(sum(loads) / len(loads), 2) if loads else 0.0

    return jsonify({
        "total_controllers": len(engine.controllers),
        "total_switches": len(engine.switches),
        "avg_load": avg_load,
        "total_migrations": len(engine.migration_history),
        "global_imbalance": round(engine._global_imbalance(), 4),
        "domain_sizes": {cid: len(sws) for cid, sws in mapping.items()},
    })


@app.route("/api/stats/timeseries")
def get_timeseries():
    """Return time-series data for the LoadChart component."""
    limit = request.args.get("limit", 60, type=int)
    with sim_lock:
        data = engine.timeseries[-limit:]
    return jsonify(data)


# =====================================================================
#  REST API — Migrations
# =====================================================================

@app.route("/api/migration/history")
def get_migration_history():
    """Return migration log entries."""
    limit = request.args.get("limit", 50, type=int)
    with sim_lock:
        data = engine.migration_history[-limit:]
    return jsonify(data)


@app.route("/api/migration/auto", methods=["POST"])
def toggle_auto_migration():
    """Toggle automatic migration on/off."""
    global auto_migration_enabled
    body = request.get_json(silent=True) or {}

    if "enabled" in body:
        auto_migration_enabled = bool(body["enabled"])
    else:
        auto_migration_enabled = not auto_migration_enabled

    logger.info("Auto-migration: %s", auto_migration_enabled)
    return jsonify({"auto_migration_enabled": auto_migration_enabled})


# =====================================================================
#  REST API — Configuration
# =====================================================================

@app.route("/api/config/traffic", methods=["POST"])
def config_traffic():
    """
    In the real Ryu+Mininet setup, traffic is generated from the Mininet CLI.
    This endpoint just returns guidance commands.
    """
    return jsonify({
        "mode": "mininet_cli",
        "message": "Traffic is generated from the Mininet CLI, not the dashboard.",
        "commands": {
            "light": "h1 ping h4 -i 0.5 &",
            "medium": "h1 ping h4 -i 0.1 & h2 ping h5 -i 0.1 &",
            "heavy": "h1 ping -f h2 & h2 ping -f h3 & h3 ping -f h1 &",
            "iperf": "h1 iperf -s & h4 iperf -c 10.0.0.1 -t 30 &",
            "stop_all": "sh killall ping iperf 2>/dev/null",
        },
    })


@app.route("/api/config/speed", methods=["POST"])
def config_speed():
    """Adjust the polling/migration check interval."""
    global polling_interval
    body = request.get_json(silent=True) or {}
    speed = float(body.get("speed", 1.0))

    if speed > 0:
        polling_interval = 1.0 / speed
        logger.info("Polling interval set to %.2fs (speed=%.1fx)", polling_interval, speed)

    return jsonify({"speed": speed, "interval": polling_interval})


@app.route("/api/config/topology", methods=["POST"])
def config_topology():
    """
    Topology is fixed in Mininet. This endpoint is a no-op
    but prevents frontend errors if the old dropdown is used.
    """
    return jsonify({
        "message": "Topology is fixed at Mininet startup. "
                   "Restart topo_multi.py with a different script to change topology.",
    })


# =====================================================================
#  WebSocket events
# =====================================================================

@socketio.on("connect")
def handle_connect():
    logger.info("Client connected: %s", request.sid)
    # Send initial topology
    socketio.emit("topology", get_topology().get_json(), to=request.sid)


@socketio.on("disconnect")
def handle_disconnect():
    logger.info("Client disconnected: %s", request.sid)


# =====================================================================
#  Background loop — snapshot + load balancing
# =====================================================================

def simulation_loop():
    """
    Background thread that periodically:
    1. Takes a snapshot of current state
    2. Runs load balancing if auto_migration is enabled
    3. Emits updates to all connected WebSocket clients
    """
    while True:
        time.sleep(polling_interval)

        with sim_lock:
            snapshot = engine.take_snapshot()
            migration_record = None

            if auto_migration_enabled:
                migration_record = engine.run_load_balancing()

        socketio.emit("state_update", {
            "snapshot": snapshot,
            "traffic": {},
            "migration": migration_record,
            "level_changes": {},
        })


# =====================================================================
#  Startup
# =====================================================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("DLBMT Dashboard Backend — Ryu + Mininet Mode")
    logger.info("=" * 60)
    logger.info("Waiting for Ryu controllers to POST to /api/ryu/update")
    logger.info("")
    logger.info("Setup sequence:")
    logger.info("  1. bash run_ryu.sh          (start 3 Ryu controllers)")
    logger.info("  2. sudo python topo_multi.py (start Mininet)")
    logger.info("  3. python app.py             (this server)")
    logger.info("  4. cd frontend && npm run dev (dashboard)")
    logger.info("")
    logger.info("Generate traffic from Mininet CLI:")
    logger.info("  mininet> h1 ping h4 -i 0.1 &")
    logger.info("  mininet> h1 ping -f h2 &  (flood for overload)")
    logger.info("=" * 60)

    # Start background loop
    bg_thread = threading.Thread(target=simulation_loop, daemon=True)
    bg_thread.start()

    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
