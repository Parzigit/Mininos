#!/usr/bin/env python3

import os
import sys
import argparse
import time
from functools import partial

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink

# Import shared topology logic
# Ensure current directory is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dlbmt_topology import get_topology

def run_topology(topo_name):
    """
    Run the specified topology using Mininet.
    """
    # Load topology data
    topo_data = get_topology(topo_name)
    config = topo_data["config"]
    controllers_data = topo_data["controllers"]
    switches_list = topo_data["switches"]
    links_list = topo_data["links"]
    assignments = topo_data["assignments"]

    info(f"*** Building Topology: {config['name']} ({len(switches_list)} switches, {len(controllers_data)} controllers)\n")

    # Initialize Mininet
    # We use build=False so we can add things manually
    net = Mininet(
        controller=None,
        switch=partial(OVSSwitch, protocols='OpenFlow13'),
        link=TCLink,
        build=False
    )

    # 1. Add Controllers
    # We need to map our "c1"..IDs to Mininet objects
    # RemoteController requires IP/Port. 
    # We assume controllers are running locally on ports 6633, 6634...
    controllers = {}
    
    for i, c_data in enumerate(controllers_data):
        cid = c_data["id"]
        # Determine port: 6633 + index
        # We assume cid is like "c1", "c2"...
        try:
            idx = int(cid[1:]) - 1
        except ValueError:
            idx = i
            
        port = 6633 + idx
        
        info(f"*** Adding controller {cid} at 127.0.0.1:{port}\n")
        c = net.addController(
            name=cid,
            controller=RemoteController,
            ip='127.0.0.1',
            port=port
        )
        controllers[cid] = c

    # 2. Add Switches
    switches = {}
    for sid in switches_list:
        # sid is "s1", "s2"... match Mininet naming
        # dpid is integer of sid
        try:
            dpid = str(int(sid[1:]))
            # dpid must be hex string for OVS usually, but Mininet handles int string too
            # or we can let Mininet assign default dpid if we name it s1
        except ValueError:
            dpid = None
            
        s = net.addSwitch(sid, dpid=dpid)
        switches[sid] = s

    # 3. Add Hosts
    # One host per switch for traffic generation
    hosts = {}
    for sid in switches_list:
        hid = f"h{sid[1:]}" # s1 -> h1
        h = net.addHost(hid, ip=f"10.0.0.{sid[1:]}")
        net.addLink(h, switches[sid])
        hosts[hid] = h

    # 4. Add Links (Switch-Switch)
    for u, v in links_list:
        if u in switches and v in switches:
            # Use some default link params (100Mbps, 1ms delay)
            net.addLink(switches[u], switches[v], bw=100, delay='1ms')
        else:
            info(f"*** Warning: Skipping link {u}-{v} (node not found)\n")

    # Build network
    info("*** Building network\n")
    net.build()

    # 5. Manual Startup (1:1 Mapping)
    # This is CRITICAL from previous debugging.
    # We must start controllers, then start switches connected ONLY to their assigned controller.
    
    info("*** Starting controllers\n")
    for c in controllers.values():
        c.start()

    info("*** Starting switches with 1:1 controller mapping\n")
    for sid, s in switches.items():
        # Get assigned controller ID
        cid = assignments.get(sid)
        if not cid or cid not in controllers:
            # Fallback to c1 or round robin?
            # assignments should be complete from dlbmt_topology
            cid = "c1"
            info(f"Warning: {sid} has no assignment, defaulting to {cid}\n")
            
        c_obj = controllers[cid]
        
        # Start switch connected ONLY to this controller
        # This prevents "all switches connect to all controllers"
        s.start([c_obj])
        
        # Set protocol again to be safe (though OVSSwitch(protocols=...) should handle it)
        s.cmd(f'ovs-vsctl set bridge {sid} protocols=OpenFlow13')

    # Configure hosts (interfaces)
    net.configHosts()

    # CLI
    info("*** Running CLI\n")
    CLI(net)

    info("*** Stopping network\n")
    net.stop()

if __name__ == "__main__":
    setLogLevel('info')
    
    parser = argparse.ArgumentParser(description="Run DLBMT Mininet Topology")
    parser.add_argument("--topo", type=str, default="atlanta", 
                        help="Topology name: atlanta, arn, germany50, interroute")
    
    args = parser.parse_args()
    
    # Run
    run_topology(args.topo)
