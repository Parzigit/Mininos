"""
DLBMT Engine — Real Ryu + Mininet Integration
===============================================
Implements Equations 1-10 and Algorithms 1-2 from the DLBMT paper
(Computer Communications 238, 2025).

Receives live metrics from Ryu controllers via the Flask endpoint
and performs actual switch migration using `ovs-vsctl`.
"""

import time
import math
import logging
import subprocess
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# =====================================================================
#  Constants & Configuration
# =====================================================================

# Multi-level thresholds — paper Section 3.2
# Level 1: Idle        [0, T_idle)
# Level 2: Normal      [T_idle, T_normal)
# Level 3: High Load   [T_normal, T_high)
# Level 4: Overload    [T_high, 100]
THRESHOLDS = [25.0, 50.0, 75.0]   # T_idle, T_normal, T_high


class ControllerLevel(IntEnum):
    IDLE = 1
    NORMAL = 2
    HIGH = 3
    OVERLOAD = 4

    @property
    def label(self):
        return {1: "Idle", 2: "Normal", 3: "High Load", 4: "Overload"}[self.value]

    @property
    def color(self):
        return {1: "#00ff88", 2: "#00d4ff", 3: "#ffaa00", 4: "#ff006e"}[self.value]


# Resource weight coefficients — paper Eq 1-3
# α (CPU) + β (Memory) + γ (Bandwidth) = 1
DEFAULT_ALPHA = 0.4
DEFAULT_BETA = 0.3
DEFAULT_GAMMA = 0.3

# Traffic-to-resource mapping factors
# Maps packet-in rate to simulated controller resource consumption.
# These align with the paper's model where packet-in requests drive load.
#
# Calibration for reaching OVERLOAD (≥75%) with `ping -f`:
#   - `ping -f` generates ~500-2000 pps per host pair
#   - 3 switches × 1500 pps = 4500 total pps on one controller
#   - CPU: 4500 × 0.05 = 225 → cpu_util = 225/100 (capped at 1.0) → weighted = 0.4
#   - MEM: 4500 × 0.005 = 22.5 MB → mem_util = 22.5/4096 → weighted ≈ 0.0016
#   - BW:  4500 × 0.05 = 225 Mbps → bw_util = 225/1000 → weighted = 0.3 × 0.225 ≈ 0.068
#   - Total load ≈ (0.4 + 0.0016 + 0.068) × 100 ≈ 47% per ~4500 pps
#   - With 6000+ pps (heavy flood): ≈ 75%+ → triggers HIGH/OVERLOAD
# Tuned for paper capacities (CPU ~2000-5000)
# Goal: ~2000 pps should trigger OVERLOAD (75%+) on a 2500 capacity node
# 2000 * 1.5 = 3000 > 2500 -> 100% utilization
TRAFFIC_TO_CPU_FACTOR = 1.5      # Each pkt/s adds 1.5 units of CPU load
TRAFFIC_TO_MEM_FACTOR = 0.4      # Each pkt/s adds 0.4 MB memory usage
TRAFFIC_TO_BW_FACTOR = 0.25      # Each pkt/s adds 0.25 Mbps bandwidth


# =====================================================================
#  Data Classes
# =====================================================================

@dataclass
class Switch:
    id: str                 # e.g. "s1"
    dpid: int               # OpenFlow datapath ID
    controller_id: str      # "c1", "c2", "c3"
    x: float = 0.0          # Position for topology rendering
    y: float = 0.0
    packet_in_rate: float = 0.0   # Packets per second (from Ryu)
    load_cpu: float = 0.0         # CPU contribution (%)
    load_mem: float = 0.0         # Memory contribution (MB)
    load_bw: float = 0.0          # Bandwidth contribution (Mbps)
    flow_count: int = 0


@dataclass
class Controller:
    id: str                   # "c1", "c2", "c3"
    rpc_port: int             # OpenFlow port (6633, 6634, 6635)
    x: float = 0.0           # Position for topology rendering
    y: float = 0.0
    active: bool = True
    # Capacities
    capacity_cpu: float = 100.0   # Max CPU (%)
    capacity_mem: float = 4096.0  # Max memory (MB)
    capacity_bw: float = 1000.0   # Max bandwidth (Mbps)
    # Current utilization (from Ryu process metrics)
    cpu_utilization: float = 0.0
    mem_utilization: float = 0.0
    bw_utilization: float = 0.0
    # Computed metrics
    load_percentage: float = 0.0
    level: ControllerLevel = ControllerLevel.IDLE
    # Timestamp of last update from Ryu
    last_update: float = 0.0


@dataclass
class MigrationRecord:
    timestamp: float
    switch_id: str
    source_controller: str
    target_controller: str
    source_load_before: float
    source_load_after: float
    target_load_before: float
    target_load_after: float
    migration_efficiency: float = 0.0
    migration_cost: float = 0.0
    imbalance_before: float = 0.0
    imbalance_after: float = 0.0

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "time_str": time.strftime("%H:%M:%S", time.localtime(self.timestamp)),
            "switch_id": self.switch_id,
            "source_controller": self.source_controller,
            "target_controller": self.target_controller,
            "source_load_before": round(self.source_load_before, 2),
            "source_load_after": round(self.source_load_after, 2),
            "target_load_before": round(self.target_load_before, 2),
            "target_load_after": round(self.target_load_after, 2),
            "migration_efficiency": round(self.migration_efficiency, 4),
            "migration_cost": round(self.migration_cost, 4),
            "imbalance_before": round(self.imbalance_before, 4),
            "imbalance_after": round(self.imbalance_after, 4),
        }


# =====================================================================
#  DLBMT Engine
# =====================================================================

class RealDLBMTEngine:
    """
    Core DLBMT engine for real Ryu + Mininet environment.

    - Receives metrics from Ryu controllers via update_controller_metrics()
    - Computes load using paper Eq 1-4
    - Determines controller levels using multi-level thresholds
    - Selects migration candidates using Algorithm 1 (Eq 5-8)
    - Executes migrations via ovs-vsctl (Algorithm 2)
    """

    def __init__(self,
                 topology_name: str = "atlanta",
                 alpha: float = DEFAULT_ALPHA,
                 beta: float = DEFAULT_BETA,
                 gamma: float = DEFAULT_GAMMA):
        self.topology_name = topology_name
        self.a = alpha
        self.b = beta
        self.c = gamma

        self.controllers: Dict[str, Controller] = {}
        self.switches: Dict[str, Switch] = {}
        self.dpid_map: Dict[int, str] = {}  # dpid -> switch id

        # Distance matrix for migration cost — d(si, cj)
        self.distances: Dict[str, Dict[str, float]] = {}

        # History
        self.migration_history: List[dict] = []
        self.timeseries: List[dict] = []
        self.max_timeseries = 120

        self._init_topology()

    # ------------------------------------------------------------------
    #  Topology Initialization (matches topo_multi.py)
    # ------------------------------------------------------------------

    def _init_topology(self):
        """
        Initialize controllers and switches based on the selected topology.
        Uses dlbmt_topology.py to ensure consistency with Mininet.
        """
        try:
            from dlbmt_topology import get_topology
        except ImportError:
            # Fallback if running where dlbmt_topology is not in path
            import sys
            sys.path.append(".")
            from dlbmt_topology import get_topology

        # Load topology data
        topo_data = get_topology(self.topology_name)
        config = topo_data["config"]
        
        logger.info(f"Initializing topology: {config['name']}")
        
        # 1. Initialize Controllers
        for c_data in topo_data["controllers"]:
            cid = c_data["id"]
            # Default rpc_port starting from 6633 based on index
            idx = int(cid[1:]) - 1
            port = 6633 + idx
            
            self.controllers[cid] = Controller(
                id=cid,
                rpc_port=port,
                x=c_data["x"],
                y=c_data["y"],
                capacity_cpu=c_data["capacity_cpu"],
                capacity_mem=c_data["capacity_mem"],
                capacity_bw=c_data["capacity_bw"],
            )

        # 2. Initialize Switches
        assignments = topo_data["assignments"]
        positions = topo_data["positions"]
        
        for sid in topo_data["switches"]:
            # Parse dpid from s1 -> 1
            try:
                dpid = int(sid[1:])
            except ValueError:
                dpid = 0
            
            # Get assignment and position
            cid = assignments.get(sid, "c1")
            pos = positions.get(sid, (0, 0))
            
            self.switches[sid] = Switch(
                id=sid,
                dpid=dpid,
                controller_id=cid,
                x=pos[0],
                y=pos[1]
            )
            self.dpid_map[dpid] = sid

        # 3. Store Infrastructure Links for Visualization
        self.infra_links = topo_data["links"] # List of (sX, sY)

        # 4. Distance matrix — shorter distances within same domain
        for sw in self.switches.values():
            self.distances[sw.id] = {}
            for ctrl in self.controllers.values():
                sx, sy = sw.x, sw.y
                cx, cy = ctrl.x, ctrl.y
                dist = math.sqrt((sx - cx) ** 2 + (sy - cy) ** 2)
                # Normalize to 0-1 range (max possible ~800)
                self.distances[sw.id][ctrl.id] = dist / 800.0

    # ------------------------------------------------------------------
    #  Infrastructure links (for topology visualization)
    # ------------------------------------------------------------------

    def get_infra_links(self):
        """Return switch-to-switch infrastructure links matching topo_multi.py."""
        return getattr(self, "infra_links", [])

    # ------------------------------------------------------------------
    #  Receive Ryu Metrics (called by Flask endpoint)
    # ------------------------------------------------------------------

    def update_controller_metrics(self, data: dict):
        """
        Receive real-time metrics from a Ryu controller instance.

        Args:
            data: {
                "controller_id": "c1",
                "cpu": 12.5,          # process CPU %
                "memory": 0.8,        # process memory %
                "switches": {"1": 150, "2": 30, ...}  # dpid -> packet_in count
            }
        """
        cid = data.get("controller_id")
        if not cid or cid not in self.controllers:
            logger.warning("Unknown controller_id: %s", cid)
            return

        ctrl = self.controllers[cid]
        ctrl.last_update = time.time()

        switches_data = data.get("switches", {})

        # ---- Update switch ownership and packet-in rates ----
        total_pkt_rate = 0.0
        total_bw = 0.0

        for dpid_str, pkt_count in switches_data.items():
            try:
                dpid = int(dpid_str)
            except ValueError:
                continue

            sid = self.dpid_map.get(dpid)
            if not sid:
                continue

            sw = self.switches.get(sid)
            if not sw:
                continue

            # Strict ownership: only process metrics from the switch's assigned controller
            if sw.controller_id != cid:
                continue

            # Packet-in rate (count per 1-second interval ≈ pps)
            sw.packet_in_rate = float(pkt_count)

            # ---- Paper Eq 1-3: Resource consumption per switch ----
            # The paper models resource consumption as a function of
            # packet-in requests from each switch.
            sw.load_cpu = sw.packet_in_rate * TRAFFIC_TO_CPU_FACTOR
            sw.load_mem = sw.packet_in_rate * TRAFFIC_TO_MEM_FACTOR
            sw.load_bw = sw.packet_in_rate * TRAFFIC_TO_BW_FACTOR

            total_pkt_rate += sw.packet_in_rate
            total_bw += sw.load_bw

        # ---- Update controller utilization ----
        # Sum resource usage across all switches in this domain
        dom_switches = [s for s in self.switches.values()
                        if s.controller_id == cid]

        total_cpu_load = sum(s.load_cpu for s in dom_switches)
        total_mem_load = sum(s.load_mem for s in dom_switches)
        total_bw_load = sum(s.load_bw for s in dom_switches)

        # Utilization = usage / capacity × 100
        ctrl.cpu_utilization = min(total_cpu_load / ctrl.capacity_cpu * 100, 100.0)
        ctrl.mem_utilization = min(total_mem_load / ctrl.capacity_mem * 100, 100.0)
        ctrl.bw_utilization = min(total_bw_load / ctrl.capacity_bw * 100, 100.0)

        # ---- Paper Eq 4: Controller load (weighted sum) ----
        self._compute_controller_load(ctrl)

    # ------------------------------------------------------------------
    #  Eq 4: Compute controller load percentage
    # ------------------------------------------------------------------

    def _compute_controller_load(self, ctrl: Controller):
        """
        Paper Eq 4: L(ci) = α·R_cpu(ci) + β·R_mem(ci) + γ·R_bw(ci)

        Where R_x(ci) = usage_x / capacity_x (normalized 0-1).
        Result scaled to 0-100%.
        """
        dom_switches = [s for s in self.switches.values()
                        if s.controller_id == ctrl.id]

        if not dom_switches:
            ctrl.load_percentage = 0.0
            ctrl.level = ControllerLevel.IDLE
            return

        # Sum resource usage from all switches
        total_cpu = sum(s.load_cpu for s in dom_switches)
        total_mem = sum(s.load_mem for s in dom_switches)
        total_bw = sum(s.load_bw for s in dom_switches)

        # Normalize by capacity
        r_cpu = min(total_cpu / ctrl.capacity_cpu, 1.0)
        r_mem = min(total_mem / ctrl.capacity_mem, 1.0)
        r_bw = min(total_bw / ctrl.capacity_bw, 1.0)

        # Weighted sum
        load = (self.a * r_cpu + self.b * r_mem + self.c * r_bw) * 100.0
        ctrl.load_percentage = min(load, 100.0)

        # Determine level based on thresholds
        if ctrl.load_percentage < THRESHOLDS[0]:
            ctrl.level = ControllerLevel.IDLE
        elif ctrl.load_percentage < THRESHOLDS[1]:
            ctrl.level = ControllerLevel.NORMAL
        elif ctrl.load_percentage < THRESHOLDS[2]:
            ctrl.level = ControllerLevel.HIGH
        else:
            ctrl.level = ControllerLevel.OVERLOAD

    # ------------------------------------------------------------------
    #  Build controller → switch mapping
    # ------------------------------------------------------------------

    def build_mapping(self) -> Dict[str, List[str]]:
        """Return {controller_id: [switch_ids]}."""
        mapping = {cid: [] for cid in self.controllers}
        for sw in self.switches.values():
            if sw.controller_id in mapping:
                mapping[sw.controller_id].append(sw.id)
        return mapping

    # ------------------------------------------------------------------
    #  Eq 5: Compute switch resource on current controller
    # ------------------------------------------------------------------

    def _switch_resource_usage(self, switch: Switch, ctrl: Controller) -> float:
        """
        Paper Eq 5: Resource usage of switch si on controller cj.
        U(si, cj) = α·(cpu_si/cap_cpu_cj) + β·(mem_si/cap_mem_cj) + γ·(bw_si/cap_bw_cj)
        """
        r_cpu = switch.load_cpu / ctrl.capacity_cpu if ctrl.capacity_cpu > 0 else 0
        r_mem = switch.load_mem / ctrl.capacity_mem if ctrl.capacity_mem > 0 else 0
        r_bw = switch.load_bw / ctrl.capacity_bw if ctrl.capacity_bw > 0 else 0
        return self.a * r_cpu + self.b * r_mem + self.c * r_bw

    # ------------------------------------------------------------------
    #  Eq 7: Predict switch resource on TARGET controller
    # ------------------------------------------------------------------

    def _switch_resource_on_target(self, switch: Switch,
                                   target: Controller) -> float:
        """
        Paper Eq 7: Predicted resource usage of si on target ck.
        Different controller may have different capacities.
        """
        r_cpu = switch.load_cpu / target.capacity_cpu if target.capacity_cpu > 0 else 0
        r_mem = switch.load_mem / target.capacity_mem if target.capacity_mem > 0 else 0
        r_bw = switch.load_bw / target.capacity_bw if target.capacity_bw > 0 else 0
        return self.a * r_cpu + self.b * r_mem + self.c * r_bw

    # ------------------------------------------------------------------
    #  Eq 6: Migration cost
    # ------------------------------------------------------------------

    def _migration_cost(self, switch: Switch, source: Controller,
                        target: Controller) -> float:
        """
        Paper Eq 6: MC(si, cj, ck) = d(si, ck) × U(si, cj)
        Migration cost = distance to target × current resource usage.
        """
        dist = self.distances.get(switch.id, {}).get(target.id, 1.0)
        usage = self._switch_resource_usage(switch, source)
        return dist * (usage + 0.001)  # small epsilon to avoid zero

    # ------------------------------------------------------------------
    #  Eq 8: Pair-wise load imbalance degree
    # ------------------------------------------------------------------

    def _pairwise_imbalance(self, c1: Controller, c2: Controller) -> float:
        """
        Paper Eq 8: DC(cj, ck) = |L(cj) - L(ck)| / max(L(cj), L(ck))
        Load imbalance degree between two controllers.
        """
        l1 = c1.load_percentage
        l2 = c2.load_percentage
        max_load = max(l1, l2)
        if max_load < 0.01:
            return 0.0
        return abs(l1 - l2) / max_load

    # ------------------------------------------------------------------
    #  Eq 9: Global imbalance degree
    # ------------------------------------------------------------------

    def _global_imbalance(self) -> float:
        """
        Paper Eq 9: D_global = max over all pairs DC(ci, cj).
        """
        active = [c for c in self.controllers.values() if c.active]
        if len(active) < 2:
            return 0.0

        max_dc = 0.0
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                dc = self._pairwise_imbalance(active[i], active[j])
                max_dc = max(max_dc, dc)
        return max_dc

    # ------------------------------------------------------------------
    #  Eq 10: Migration efficiency
    # ------------------------------------------------------------------

    def _migration_efficiency(self, switch: Switch, source: Controller,
                              target: Controller) -> float:
        """
        Paper Eq 10: ME(si, cj, ck) = MC(si, cj, ck) / ΔDC(cj, ck)
        Lower is better — less cost for more imbalance improvement.
        """
        cost = self._migration_cost(switch, source, target)

        # Predicted loads after migration
        sw_usage_source = self._switch_resource_usage(switch, source)
        sw_usage_target = self._switch_resource_on_target(switch, target)

        pred_source_load = max(source.load_percentage - sw_usage_source * 100, 0)
        pred_target_load = min(target.load_percentage + sw_usage_target * 100, 100)

        # Current pair-wise imbalance
        dc_before = self._pairwise_imbalance(source, target)

        # Predicted pair-wise imbalance
        max_pred = max(pred_source_load, pred_target_load)
        if max_pred < 0.01:
            dc_after = 0.0
        else:
            dc_after = abs(pred_source_load - pred_target_load) / max_pred

        delta_dc = dc_before - dc_after
        if delta_dc <= 0.001:
            return float("inf")  # Migration would make things worse

        return cost / delta_dc

    # ------------------------------------------------------------------
    #  Algorithm 1: Find best migration candidate
    # ------------------------------------------------------------------

    def _find_best_migration(self, source: Controller):
        """
        Paper Algorithm 1: Select optimal (switch, target_controller) pair.

        For the overloaded/high-load source controller:
        1. Consider each switch in its domain
        2. For each switch, consider all idle/normal controllers as targets
        3. Verify migration doesn't overload target (Eq 7)
        4. Pick the pair with lowest migration efficiency (Eq 10)
        """
        dom_switches = [s for s in self.switches.values()
                        if s.controller_id == source.id]

        if not dom_switches:
            return None

        # Candidate targets: idle or normal controllers (not the source)
        targets = [c for c in self.controllers.values()
                   if c.active
                   and c.id != source.id
                   and c.level in (ControllerLevel.IDLE, ControllerLevel.NORMAL)]

        if not targets:
            return None

        best = None
        best_efficiency = float("inf")

        for sw in dom_switches:
            for tgt in targets:
                # Check: would migration overload the target? (Eq 7)
                added_load = self._switch_resource_on_target(sw, tgt) * 100
                pred_target = tgt.load_percentage + added_load

                if pred_target >= THRESHOLDS[2]:  # Would push target to HIGH/OVERLOAD
                    continue

                # Compute migration efficiency (Eq 10)
                eff = self._migration_efficiency(sw, source, tgt)
                if eff < best_efficiency:
                    best_efficiency = eff
                    cost = self._migration_cost(sw, source, tgt)

                    sw_usage_src = self._switch_resource_usage(sw, source)
                    sw_usage_tgt = self._switch_resource_on_target(sw, tgt)

                    best = (sw, tgt, eff, {
                        "cost": cost,
                        "efficiency": eff,
                        "pred_src": max(source.load_percentage - sw_usage_src * 100, 0),
                        "pred_tgt": min(tgt.load_percentage + sw_usage_tgt * 100, 100),
                        "dc_before": self._pairwise_imbalance(source, tgt),
                    })

        return best

    # ------------------------------------------------------------------
    #  Algorithm 2: Execute migration
    # ------------------------------------------------------------------

    def _execute_migration(self, switch: Switch, source: Controller,
                           target: Controller, data: dict) -> Optional[dict]:
        """
        Paper Algorithm 2: Execute the switch migration via ovs-vsctl.
        """
        dc_before = data.get("dc_before", 0)

        cmd = [
            "sudo", "ovs-vsctl", "set-controller",
            switch.id, f"tcp:127.0.0.1:{target.rpc_port}"
        ]
        logger.info("Executing migration: %s", " ".join(cmd))

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=10)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.error("Migration failed: %s", e)
            return None

        # Update internal state
        old_controller = switch.controller_id
        switch.controller_id = target.id

        # Recompute loads after migration
        self._compute_controller_load(source)
        self._compute_controller_load(target)

        dc_after = self._pairwise_imbalance(source, target)

        record = MigrationRecord(
            timestamp=time.time(),
            switch_id=switch.id,
            source_controller=source.id,
            target_controller=target.id,
            source_load_before=data.get("pred_src", source.load_percentage),
            source_load_after=source.load_percentage,
            target_load_before=data.get("pred_tgt", target.load_percentage),
            target_load_after=target.load_percentage,
            migration_efficiency=data.get("efficiency", 0),
            migration_cost=data.get("cost", 0),
            imbalance_before=dc_before,
            imbalance_after=dc_after,
        )

        rec_dict = record.to_dict()
        self.migration_history.append(rec_dict)
        logger.info("Migration complete: %s %s→%s", switch.id, old_controller, target.id)
        return rec_dict

    # ------------------------------------------------------------------
    #  Main load balancing loop
    # ------------------------------------------------------------------

    def run_load_balancing(self) -> Optional[dict]:
        """
        Paper Algorithms 1 + 2 combined:
        1. Find controllers in HIGH or OVERLOAD state
        2. For each, find the best migration candidate
        3. Execute the single best migration (greedy, one per cycle)
        """
        # Ensure all loads are current
        for ctrl in self.controllers.values():
            self._compute_controller_load(ctrl)

        # Identify overloaded/high-load controllers
        sources = [c for c in self.controllers.values()
                   if c.active
                   and c.level in (ControllerLevel.HIGH, ControllerLevel.OVERLOAD)]

        if not sources:
            return None

        # Find the globally best migration across all source controllers
        best_pair = None
        best_eff = float("inf")

        for src in sources:
            result = self._find_best_migration(src)
            if result:
                sw, tgt, eff, extra = result
                if eff < best_eff:
                    best_eff = eff
                    best_pair = (sw, src, tgt, extra)

        if best_pair:
            return self._execute_migration(*best_pair)

        return None

    # ------------------------------------------------------------------
    #  Snapshot for frontend
    # ------------------------------------------------------------------

    def take_snapshot(self) -> dict:
        """
        Build a state snapshot used by the Flask API.
        Compatible with the frontend's expected data structure.
        """
        mapping = self.build_mapping()
        domain_sizes = {cid: len(sws) for cid, sws in mapping.items()}

        ctrl_data = {}
        for ctrl in self.controllers.values():
            ctrl_data[ctrl.id] = {
                "load": round(ctrl.load_percentage, 2),
                "level": ctrl.level.value,
                "level_label": ctrl.level.label,
                "level_color": ctrl.level.color,
                "switch_count": domain_sizes.get(ctrl.id, 0),
                "cpu_utilization": round(ctrl.cpu_utilization, 2),
                "mem_utilization": round(ctrl.mem_utilization, 2),
                "bw_utilization": round(ctrl.bw_utilization, 2),
            }

        # Compute aggregate stats
        loads = [c.load_percentage for c in self.controllers.values() if c.active]
        avg_load = round(sum(loads) / len(loads), 2) if loads else 0.0

        snapshot = {
            "timestamp": time.time(),
            "controllers": ctrl_data,
            "domain_sizes": domain_sizes,
            "avg_load": avg_load,
            "global_imbalance": round(self._global_imbalance(), 4),
        }

        # Append to timeseries
        self.timeseries.append(snapshot)
        if len(self.timeseries) > self.max_timeseries:
            self.timeseries = self.timeseries[-self.max_timeseries:]

        return snapshot
