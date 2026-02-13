"""
DLBMT Topology Generator
========================
Provides a single source of truth for the 4 paper topologies:
- Atlanta (15 nodes, 22 edges, 3 controllers)
- ARN (30 nodes, 29 edges, 4 controllers)
- Germany50 (50 nodes, 88 edges, 5 controllers)
- Interroute (110 nodes, 159 edges, 7 controllers)

Reproducible generation using seed=42.
Dependencies: networkx (optional, falls back if missing)
"""

import random
import math
from typing import Dict, List, Tuple, Any

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False

# ---------------------------------------------------------------------------
# Topology Configurations (from Paper/Simulator)
# ---------------------------------------------------------------------------

TOPOLOGIES = {
    "atlanta": {
        "name": "Atlanta",
        "nodes": 15,
        "edges": 22,
        "controllers": 3,
        "capacities": [
            {"cpu": 2000, "mem": 4096, "bw": 1000},
            {"cpu": 2000, "mem": 4096, "bw": 1000},
            {"cpu": 2500, "mem": 4096, "bw": 1200},
        ],
    },
    "arn": {
        "name": "ARN",
        "nodes": 30,
        "edges": 29,  # Note: Less edges than nodes means disconnected or tree? Simulator says 29. A tree of 30 nodes has 29 edges.
        "controllers": 4,
        "capacities": [
            {"cpu": 2500, "mem": 4096, "bw": 1200},
            {"cpu": 2500, "mem": 4096, "bw": 1200},
            {"cpu": 2500, "mem": 4096, "bw": 1200},
            {"cpu": 3000, "mem": 8192, "bw": 1500},
        ],
    },
    "germany50": {
        "name": "Germany50",
        "nodes": 50,
        "edges": 88,
        "controllers": 5,
        "capacities": [
            {"cpu": 3000, "mem": 8192, "bw": 1500},
            {"cpu": 3000, "mem": 8192, "bw": 1500},
            {"cpu": 3000, "mem": 8192, "bw": 1500},
            {"cpu": 3500, "mem": 8192, "bw": 2000},
            {"cpu": 4000, "mem": 16384, "bw": 2000},
        ],
    },
    "interroute": {
        "name": "Interroute",
        "nodes": 110,
        "edges": 159,
        "controllers": 7,
        "capacities": [
            {"cpu": 4000, "mem": 16384, "bw": 2000},
            {"cpu": 4000, "mem": 16384, "bw": 2000},
            {"cpu": 4000, "mem": 16384, "bw": 2000},
            {"cpu": 4000, "mem": 16384, "bw": 2000},
            {"cpu": 4000, "mem": 16384, "bw": 2000},
            {"cpu": 5000, "mem": 32768, "bw": 3000},
            {"cpu": 5000, "mem": 32768, "bw": 3000},
        ],
    },
    # Default small topology for testing (matches current topo_multi.py)
    "custom": {
        "name": "Custom 9-Switch",
        "nodes": 9,
        "edges": 8, # Tree
        "controllers": 3,
        "capacities": [
            {"cpu": 100, "mem": 4096, "bw": 100},
            {"cpu": 100, "mem": 4096, "bw": 100},
            {"cpu": 100, "mem": 4096, "bw": 100},
        ]
    }
}


def get_topology(name: str) -> Dict[str, Any]:
    """
    Generate topology data deterministically.
    
    Returns a dict with:
      - config: full topology config from TOPOLOGIES
      - switches: list of "sX" IDs
      - controllers: list of dicts (id, capacities, switch_ids, x, y)
      - links: list of (u, v) tuples where u,v are "sX" or "cX"
      - positions: dict of {node_id: (x, y)}
    """
    if name not in TOPOLOGIES:
        name = "atlanta" # Default
    
    config = TOPOLOGIES[name]
    num_nodes = config["nodes"]
    num_edges = config["edges"]
    num_ctrls = config["controllers"]

    # Seed random generator for reproducibility
    rng = random.Random(42)

    # Generate Edges (Graph)
    edges = []
    if HAS_NETWORKX:
        G = _generate_nx_graph(num_nodes, num_edges, rng)
        # Calculate Layout
        pos_map = nx.spring_layout(G, k=1.5/math.sqrt(num_nodes), seed=42)
        # Scale to 100-900
        positions = _scale_positions(pos_map, 100, 900, 100, 500)
        # Convert G edges to list
        node_edges = list(G.edges())
    else:
        # Fallback: simple random graph
        node_edges = _generate_simple_graph(num_nodes, num_edges, rng)
        positions = _generate_random_positions(num_nodes, rng)
        # Compute distances for assignment? Or just random assignment?
        # We need distances for "nearest controller" logic.
        # Simple Euclidean distance with positions works.
    
    # Identify Controller Nodes
    # Use degree centrality (highest degree nodes are controllers)
    node_degrees = {}
    for u, v in node_edges:
        node_degrees[u] = node_degrees.get(u, 0) + 1
        node_degrees[v] = node_degrees.get(v, 0) + 1
    
    # Sort nodes by degree
    sorted_nodes = sorted(range(num_nodes), key=lambda n: node_degrees.get(n, 0), reverse=True)
    ctrl_node_indices = sorted_nodes[:num_ctrls]
    
    # Map node indices to IDs
    # c1..ck, s1..sn
    # Wait, in the simulator, nodes are nodes. Some are controllers, others are switches.
    # In Mininet, controllers are separate entities.
    # We will treat the graph nodes as SWITCHES, and attach controllers to the "controller nodes".
    # Or should we treat high-degree nodes AS controllers?
    # Simulator: "Use nodes with highest degree as controllers... Assign remaining nodes as switches to nearest controller"
    # This implies high-degree nodes are REPLACED by controllers? Or controllers are placed THERE?
    # Let's assume we place controllers AT those locations, and they manage that switch + others.
    # But Mininet topology separates switch and controller.
    # We'll stick to: 'c1' manages a cluster around node X.
    
    controllers = []
    switches = []
    switch_assignments = {} # switch_id -> controller_id

    # Create Controller definitions
    for i, node_idx in enumerate(ctrl_node_indices):
        cid = f"c{i+1}"
        cap = config["capacities"][i]
        x, y = positions[node_idx]
        controllers.append({
            "id": cid,
            "capacity_cpu": cap["cpu"],
            "capacity_mem": cap["mem"],
            "capacity_bw": cap["bw"],
            "x": x,
            "y": y,
            "node_idx": node_idx # The central node for this domain
        })
    
    # Identify Switch Nodes (all nodes in graph are switches in Mininet)
    # The "controller node" concepts in simulator usually meant placement.
    # So we have N switches. We place K controllers.
    # Assign each switch to nearest controller.
    
    switch_list = []
    for i in range(num_nodes):
        sid = f"s{i+1}"
        x, y = positions[i]
        
        # Find nearest controller
        best_ctrl = None
        min_dist = float('inf')
        
        for ctrl in controllers:
            cx, cy = ctrl['x'], ctrl['y']
            dist = math.sqrt((x - cx)**2 + (y - cy)**2)
            if dist < min_dist:
                min_dist = dist
                best_ctrl = ctrl['id']
        
        switch_list.append(sid)
        switch_assignments[sid] = best_ctrl
        
        # Update controller list with this switch
        # (Not strictly needed here, but helpful)

    # Format Links (sX, sY)
    formatted_links = []
    for u, v in node_edges:
        formatted_links.append((f"s{u+1}", f"s{v+1}"))
    
    return {
        "config": config,
        "switches": switch_list,
        "controllers": controllers,
        "links": formatted_links,
        "assignments": switch_assignments,
        "positions": {f"s{i+1}": positions[i] for i in range(num_nodes)}
    }


def _generate_nx_graph(n, e, rng):
    """Generate graph using NetworkX."""
    # Start with tree to ensure connectivity
    G = nx.Graph()
    nodes = list(range(n))
    G.add_nodes_from(nodes)
    
    # Spanning tree
    shuffled = nodes[:]
    rng.shuffle(shuffled)
    for i in range(1, len(shuffled)):
        G.add_edge(shuffled[i-1], shuffled[i])
        
    # Add random edges
    curr_edges = n - 1
    attempts = 0
    while curr_edges < e and attempts < e * 10:
        u = rng.randint(0, n-1)
        v = rng.randint(0, n-1)
        if u != v and not G.has_edge(u, v):
            G.add_edge(u, v)
            curr_edges += 1
        attempts += 1
    return G

def _generate_simple_graph(n, e, rng):
    """Fallback generator."""
    edges = set()
    shuffled = list(range(n))
    rng.shuffle(shuffled)
    
    # Spanning tree
    for i in range(1, len(shuffled)):
        u, v = shuffled[i-1], shuffled[i]
        if u > v: u, v = v, u
        edges.add((u, v))
        
    curr_edges = n - 1
    attempts = 0
    while curr_edges < e and attempts < e * 10:
        u = rng.randint(0, n-1)
        v = rng.randint(0, n-1)
        if u != v:
            if u > v: u, v = v, u
            if (u, v) not in edges:
                edges.add((u, v))
                curr_edges += 1
        attempts += 1
    return list(edges)

def _generate_random_positions(n, rng):
    """Fallback random positions."""
    pos = {}
    for i in range(n):
        pos[i] = (rng.uniform(100, 900), rng.uniform(100, 500))
    return pos

def _scale_positions(pos_map, xmin, xmax, ymin, ymax):
    xs = [p[0] for p in pos_map.values()]
    ys = [p[1] for p in pos_map.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    range_x = max_x - min_x if max_x > min_x else 1.0
    range_y = max_y - min_y if max_y > min_y else 1.0
    
    scaled = {}
    for node, (x, y) in pos_map.items():
        sx = xmin + (xmax - xmin) * (x - min_x) / range_x
        sy = ymin + (ymax - ymin) * (y - min_y) / range_y
        scaled[node] = (round(sx, 1), round(sy, 1))
    return scaled

if __name__ == "__main__":
    # Test
    topo = get_topology("atlanta")
    print(f"Topology: {topo['config']['name']}")
    print(f"Nodes: {len(topo['switches'])}")
    print(f"Edges: {len(topo['links'])}")
    print(f"Controllers: {len(topo['controllers'])}")
    print("Sample Link:", topo['links'][0] if topo['links'] else "None")
