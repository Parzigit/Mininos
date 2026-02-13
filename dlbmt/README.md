# DLBMT: Distributed Load Balancing Mechanism with Multi-level Thresholds (Mininet + Ryu)

This project is a high-fidelity implementation of the **DLBMT** algorithm using **Mininet** (for network emulation) and **Ryu** (for SDN control), replacing the static mathematical simulation originally provided.

## How it Differs from the Original ZIP

The original project (main) was a **Python-based mathematical simulation**. It calculated load and migrations based on formulas without any real network traffic or control plane interaction.

| Feature | Original ZIP (`sdn_simulator.py`) | This Project (`dlbmt/`) |
|---------|-----------------------------------|-------------------------|
| **Core** | Static Python script | **Mininet** (Network Emulator) + **Ryu** (SDN Controller) |
| **Traffic** | Simulated using random numbers | **Real Packets** (ICMP/Ping, TCP/UDP via `iperf`) |
| **Switches** | Python objects | **Open vSwitch (OVS)** instances |
| **Controllers** | Python objects | **Ryu Controller** processes |
| **Metrics** | Calculated internally | **Live OpenFlow Stats** (Packet-In rates) |
| **Migration** | Python list manipulation | **Real Switch Migration** (via `ovs-vsctl`) |
| **Topology** | Hardcoded logic | **Dynamic** (Atlanta, ARN, Germany50, Interroute) |
| **Visuals** | Matplotlib plots | **Real-time React Dashboard** |

---

## Architecture

1.  **Network Layer**: Mininet creates a virtual network with Open vSwitch instances.
2.  **Control Plane**: Multiple Ryu controller instances (c1, c2...) manage subsets of switches.
3.  **Metrics Collector**: Ryu controllers send live packet-in statistics to a central Flask backend.
4.  **DLBMT Engine**: The backend runs the DLBMT algorithm (Equations 1-10) to detect overload and trigger migrations.
5.  **Dashboard**: A React frontend visualizes the topology, controller load, and migration events in real-time.

---

## Installation

### Prerequisites

*   Ubuntu/Linux (Required for Mininet)
*   Python 3.8+
*   Node.js 16+

```bash
# System Dependencies
sudo apt update
sudo apt install mininet openvswitch-switch npm

# Python Dependencies
pip install ryu psutil flask flask-cors flask-socketio requests networkx
```

---

## Running the Project

You need **4 Terminal Windows** to run the full stack.

### 1. Launch Controllers (Terminal 1)
Starts the Ryu controllers. Specify the number of controllers based on the topology you want to run.

**Controller Counts:**
*   **Atlanta**: 3 (Default)
*   **ARN**: 4
*   **Germany50**: 5
*   **Interroute**: 7

```bash
cd dlbmt
export NUM_CONTROLLERS=4  # Example for ARN
./run_ryu.sh
```

### 2. Start Mininet Topology (Terminal 2)
Creates the virtual network. Matches the controller count above.

```bash
cd dlbmt
sudo python3 topo_multi.py --topo arn  # Options: atlanta, arn, germany50, interroute
```
*   _Note: The `mininet>` prompt will appear. You can run commands like `h1 ping h2` here._

### 3. Start Backend Engine (Terminal 3)
Runs the DLBMT logic and API server.

```bash
cd dlbmt
export DLBMT_TOPO=arn  # Must match the topology above
python3 app.py
```

### 4. Start Frontend Dashboard (Terminal 4)
Launches the web UI.

```bash
cd dlbmt/frontend
npm run dev
```
*   **Access the Dashboard:** Open `http://localhost:3000` in your browser.

---

## Generating Traffic

To see the loadbalancer in action, generate traffic from the Mininet CLI (Terminal 2):

*   **Light Load:** `h1 ping h2`
*   **Heavy Load (Triggers Migration):**
    ```bash
    h1 ping -f h2 &
    h2 ping -f h3 &
    h3 ping -f h1 &
    ```
    *(The `-f` flood option generates thousands of packets per second, spiking controller load)*

---

*   **Low Load**: Ensure you are using `ping -f` for stress testing. Standard pings are too lightweight to trigger migration.
